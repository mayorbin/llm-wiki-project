# backend/tests/unit/test_graph_api.py
"""图谱服务测试。"""
import pytest
from pathlib import Path
from app.config import reset_settings, get_settings
from app.storage.database import init_db, close_all_db
from app.storage.file_storage import atomic_write
from app.services.auth_service import register_user
from app.services import project_service as psvc
from app.services import graph_service as svc


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


class TestGraphData:
    """图谱数据查询测试。"""

    def test_空项目返回空图谱(self):
        """无 wiki 页面的项目应返回空图谱。"""
        user, project = _create_user_and_project("alice", "Proj")
        data = svc.get_graph_data(project["id"], user.id)
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_无权访问时拒绝(self):
        """未加入项目的用户不能查看图谱。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        project = psvc.create_project("Proj", "", u1.id)

        with pytest.raises(PermissionError):
            svc.get_graph_data(project["id"], u2.id)


class TestGraphBuild:
    """图谱构建测试。"""

    def test_构建图谱成功(self):
        """有 wiki 页面时应能成功构建图谱。"""
        user, project = _create_user_and_project("bob", "Proj")
        _create_test_page(project["id"], "sources/SourceA.md",
                          "# Source A\n\nContent with [[EntityX]]")
        _create_test_page(project["id"], "entities/EntityX.md",
                          "# Entity X\n\nReferenced by [[SourceA]]")

        data = svc.build_graph(project["id"], user.id, run_inference=False)

        assert data["stats"]["node_count"] >= 2
        assert data["stats"]["edge_count"] >= 1
        assert data["stats"]["extracted_edges"] >= 1

    def test_viewer不能构建图谱(self):
        """viewer 无权构建图谱。"""
        owner = register_user("owner1", "pw123")
        viewer = register_user("viewer1", "pw123")
        project = psvc.create_project("Proj", "", owner.id)
        psvc.add_member(project["id"], owner.id, viewer.id, "viewer")

        with pytest.raises(PermissionError):
            svc.build_graph(project["id"], viewer.id)


class TestGraphStats:
    """图谱统计测试。"""

    def test_获取统计信息(self):
        """应能获取图谱统计信息。"""
        user, project = _create_user_and_project("carol", "Proj")
        _create_test_page(project["id"], "sources/Page1.md", "# Page 1\nContent")
        _create_test_page(project["id"], "concepts/Idea.md", "# Idea\nDetails")

        svc.build_graph(project["id"], user.id, run_inference=False)
        stats = svc.get_graph_stats(project["id"], user.id)

        assert stats["node_count"] >= 2
        assert stats["graph_json_exists"] is True
        assert stats["wiki_directory_exists"] is True
