# backend/tests/unit/test_knowledge.py
"""知识查询服务测试。"""
import pytest
from pathlib import Path
from app.config import reset_settings, get_settings
from app.storage.database import init_db, close_all_db
from app.storage.file_storage import atomic_write
from app.services.auth_service import register_user
from app.services import project_service as psvc
from app.services import query_service as svc


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch, tmp_path):
    """每个测试使用独立的临时数据和密钥。"""
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-must-be-32-chars!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-dummy")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


def _create_user_and_project(username="alice", project_name="测试项目"):
    """创建用户和项目。"""
    user = register_user(username, "password123", username)
    project = psvc.create_project(project_name, "desc", user.id)
    return user, project


def _wiki_dir(project_id: str) -> Path:
    """获取项目的 wiki 目录。"""
    settings = get_settings()
    return Path(settings.data_dir) / "projects" / project_id / "wiki"


def _create_test_page(project_id: str, rel_path: str, content: str):
    """在 wiki 目录下创建测试页面。"""
    wiki = _wiki_dir(project_id)
    page = wiki / rel_path
    page.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(page, content)


class TestPageTree:
    """页面目录树测试。"""

    def test_空项目页面树(self):
        """新项目的 wiki 目录可能有基础文件但不一定有页面。"""
        user, project = _create_user_and_project("alice", "Proj")
        tree = svc.get_page_tree(project["id"], user.id)
        assert "sections" in tree

    def test_含页面时正确统计(self):
        """有页面后应能正确列出。"""
        user, project = _create_user_and_project("bob", "Proj")
        _create_test_page(project["id"], "sources/TestPage.md", "# Test\nContent")
        _create_test_page(project["id"], "concepts/Concept.md", "# Concept")

        tree = svc.get_page_tree(project["id"], user.id)
        assert tree["sections"]["sources"]["count"] >= 1
        assert tree["sections"]["concepts"]["count"] >= 1

    def test_无权访问时拒绝(self):
        """未加入项目的用户不能查看页面树。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        project = psvc.create_project("Proj", "", u1.id)

        with pytest.raises(PermissionError):
            svc.get_page_tree(project["id"], u2.id)


class TestPageCRUD:
    """页面 CRUD 测试。"""

    def test_读取页面(self):
        """应能读取已创建的页面内容。"""
        user, project = _create_user_and_project("carol", "Proj")
        content = "---\ntitle: Test\n---\n\n## Summary\nHello [[World]]"
        _create_test_page(project["id"], "sources/TestPage.md", content)

        page = svc.get_page(project["id"], user.id, "sources/TestPage.md")
        assert "Hello" in page["content"]
        assert "World" in page["wikilinks"]

    def test_不存在的页面返回错误(self):
        """读取不存在的页面应抛出 ValueError。"""
        user, project = _create_user_and_project("dave", "Proj")
        with pytest.raises(ValueError, match="不存在"):
            svc.get_page(project["id"], user.id, "ghost.md")

    def test_编辑页面(self):
        """owner 应能编辑页面内容。"""
        user, project = _create_user_and_project("eve", "Proj")
        _create_test_page(project["id"], "sources/EditMe.md", "# Old")

        result = svc.update_page(
            project["id"], user.id,
            "sources/EditMe.md", "# New Content\n\n[[OtherPage]]",
        )
        assert "sha256" in result
        assert "OtherPage" in result["wikilinks"]

        # 验证内容已更新
        page = svc.get_page(project["id"], user.id, "sources/EditMe.md")
        assert "New Content" in page["content"]

    def test_编辑历史记录(self):
        """编辑后应有历史记录。"""
        user, project = _create_user_and_project("frank", "Proj")
        _create_test_page(project["id"], "sources/HistoryPage.md", "# V1")

        svc.update_page(project["id"], user.id, "sources/HistoryPage.md", "# V2")
        history = svc.get_page_history(project["id"], user.id, "sources/HistoryPage.md")

        assert history["edits"] >= 1
        assert len(history["history"]) >= 1

    def test_viewer不能编辑页面(self):
        """viewer 无权编辑页面。"""
        owner = register_user("owner1", "pw123")
        viewer = register_user("viewer1", "pw123")
        project = psvc.create_project("Proj", "", owner.id)
        psvc.add_member(project["id"], owner.id, viewer.id, "viewer")
        _create_test_page(project["id"], "sources/ReadOnly.md", "# Content")

        with pytest.raises(PermissionError):
            svc.update_page(project["id"], viewer.id, "sources/ReadOnly.md", "# Hacked")
