# backend/tests/unit/test_files.py
"""文件服务测试。"""
import io
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.auth_service import register_user
from app.services import project_service as psvc
from app.services import file_service as svc


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


def _upload_text_file(project_id, user_id, content, filename="test.md"):
    """上传一个文本文件作为测试。"""
    f = io.BytesIO(content.encode("utf-8"))
    return svc.upload_file(project_id, user_id, f, filename)


class TestDirectoryManagement:
    """目录管理测试。"""

    def test_获取初始目录树(self):
        """新建项目应有空的 raw/ 目录。"""
        user, project = _create_user_and_project("alice", "Proj")
        tree = svc.list_directory_tree(project["id"], user.id)
        assert "directories" in tree

    def test_创建和删除子目录(self):
        """可以创建子目录，并在为空时删除。"""
        user, project = _create_user_and_project("bob", "Proj")
        svc.create_directory(project["id"], user.id, "sub1")
        tree = svc.list_directory_tree(project["id"], user.id)
        dirs = [d["name"] for d in tree.get("directories", [])]
        assert "sub1" in dirs

        svc.delete_directory(project["id"], user.id, "sub1")
        tree2 = svc.list_directory_tree(project["id"], user.id)
        dirs2 = [d["name"] for d in tree2.get("directories", [])]
        assert "sub1" not in dirs2

    def test_删除非空目录失败(self):
        """不能删除包含文件的目录。"""
        user, project = _create_user_and_project("carol", "Proj")
        svc.create_directory(project["id"], user.id, "sub2")
        # 上传文件到 sub2 子目录
        f = io.BytesIO(b"content")
        svc.upload_file(project["id"], user.id, f, "test.md", subdir="sub2")

        with pytest.raises(ValueError, match="非空"):
            svc.delete_directory(project["id"], user.id, "sub2")

    def test_无权访问项目时拒绝操作(self):
        """未加入项目的用户不能操作文件系统。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        project = psvc.create_project("Proj", "", u1.id)

        with pytest.raises(PermissionError):
            svc.create_directory(project["id"], u2.id, "sub")


class TestFileUpload:
    """文件上传测试。"""

    def test_上传文件成功(self):
        """上传 .md 文件应返回正确的元数据。"""
        user, project = _create_user_and_project("dave", "Proj")
        f = io.BytesIO("# Hello World".encode("utf-8"))
        result = svc.upload_file(project["id"], user.id, f, "hello.md")

        assert result["name"] == "hello.md"
        assert result["size_bytes"] > 0
        assert "sha256" in result
        assert result["path"] == "hello.md"

    def test_拒绝不支持的文件类型(self):
        """应拒绝白名单外的文件扩展名。"""
        user, project = _create_user_and_project("eve", "Proj")
        f = io.BytesIO(b"binary data")
        with pytest.raises(ValueError, match="不支持"):
            svc.upload_file(project["id"], user.id, f, "script.exe")

    def test_重名文件自动重命名(self):
        """上传重名文件时应自动追加后缀。"""
        user, project = _create_user_and_project("frank", "Proj")
        f1 = io.BytesIO(b"v1")
        f2 = io.BytesIO(b"v2")
        r1 = svc.upload_file(project["id"], user.id, f1, "doc.md")
        r2 = svc.upload_file(project["id"], user.id, f2, "doc.md")

        assert r1["name"] == "doc.md"
        # 第二个文件应被重命名
        assert r2["name"] != r1["name"]
        assert r2["name"].startswith("doc_")


class TestFileList:
    """文件列表测试。"""

    def test_分页列出文件(self):
        """文件列表应正确分页。"""
        user, project = _create_user_and_project("george", "Proj")
        for i in range(5):
            _upload_text_file(project["id"], user.id, f"content{i}", f"file_{i}.md")

        result = svc.list_files(project["id"], user.id, limit=3)
        assert len(result["files"]) == 3
        assert result["total"] == 5

    def test_空目录返回空列表(self):
        """空 raw/ 目录应返回空文件列表。"""
        user, project = _create_user_and_project("henry", "Proj")
        result = svc.list_files(project["id"], user.id)
        assert result["files"] == []
        assert result["total"] == 0


class TestFileOperations:
    """文件操作测试。"""

    def test_获取文件详情(self):
        """文件详情应包含 SHA256 和元数据。"""
        user, project = _create_user_and_project("iris", "Proj")
        _upload_text_file(project["id"], user.id, "hello", "info.md")

        detail = svc.get_file_detail(project["id"], user.id, "info.md")
        assert detail["name"] == "info.md"
        assert "sha256" in detail
        assert detail["size_bytes"] > 0

    def test_移动文件(self):
        """文件应能移动到子目录。"""
        user, project = _create_user_and_project("jack", "Proj")
        _upload_text_file(project["id"], user.id, "data", "data.txt")

        svc.create_directory(project["id"], user.id, "archive")
        result = svc.move_file(project["id"], user.id, "data.txt", "archive")
        assert result["destination"].startswith("archive/")

    def test_删除文件(self):
        """删除文件后文件应不存在。"""
        user, project = _create_user_and_project("kate", "Proj")
        _upload_text_file(project["id"], user.id, "tmp", "remove_me.md")

        svc.delete_file(project["id"], user.id, "remove_me.md")
        with pytest.raises(ValueError, match="不存在"):
            svc.get_file_detail(project["id"], user.id, "remove_me.md")

    def test_文件不存在时报错(self):
        """查询不存在的文件应抛出 ValueError。"""
        user, project = _create_user_and_project("leo", "Proj")
        with pytest.raises(ValueError, match="不存在"):
            svc.get_file_detail(project["id"], user.id, "ghost.md")


class TestChangeDetection:
    """变更检测测试。"""

    def test_检测新增文件(self):
        """新增文件应被检测到。"""
        user, project = _create_user_and_project("mike", "Proj")
        _upload_text_file(project["id"], user.id, "v1", "new.md")

        changes = svc.detect_changes(project["id"], user.id)
        assert len(changes["added"]) >= 1

    def test_再次检测无变更(self):
        """连续两次检测应无变更。"""
        user, project = _create_user_and_project("nancy", "Proj")
        _upload_text_file(project["id"], user.id, "v1", "stable.md")
        svc.detect_changes(project["id"], user.id)  # 保存快照

        changes2 = svc.detect_changes(project["id"], user.id)
        assert len(changes2["changed"]) == 0
        assert len(changes2["added"]) == 0
