# backend/tests/unit/test_maintenance.py
"""维护服务测试。"""
import io
import json
import pytest
import tarfile
from pathlib import Path
from app.config import reset_settings, get_settings
from app.storage.database import init_db, close_all_db, get_db
from app.storage.file_storage import atomic_write
from app.services.auth_service import register_user
from app.services import project_service as psvc
from app.services import backup_service as svc


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


class TestBackupExport:
    """备份导出测试。"""

    def test_导出空项目(self):
        """空项目应能成功导出 tar.gz。"""
        user, project = _create_user_and_project("alice", "Proj")
        name, path = svc.export_backup(project["id"], user.id)
        assert path.exists()
        assert name.endswith(".tar.gz")

        # 验证 tar.gz 内容
        with tarfile.open(str(path), "r:gz") as tar:
            names = tar.getnames()
            assert "project_meta.json" in names

    def test_导出有内容项目(self):
        """有 wiki 页面的项目应能完整导出。"""
        user, project = _create_user_and_project("bob", "Proj")

        # 创建 wiki 页面
        wiki = _wiki_dir(project["id"])
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "sources").mkdir(exist_ok=True)
        atomic_write(wiki / "sources" / "Test.md", "# Test\nContent")

        # 创建 raw 文件
        settings = get_settings()
        raw_dir = Path(settings.data_dir) / "projects" / project["id"] / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "doc.md").write_text("# Doc", encoding="utf-8")

        name, path = svc.export_backup(project["id"], user.id)
        assert path.exists()

        with tarfile.open(str(path), "r:gz") as tar:
            names = tar.getnames()
            assert any(n.startswith("wiki/") for n in names)
            assert any(n.startswith("raw/") for n in names)

    def test_无权访问时拒绝导出(self):
        """未加入项目的用户不能导出。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        project = psvc.create_project("Proj", "", u1.id)

        with pytest.raises(PermissionError):
            svc.export_backup(project["id"], u2.id)


class TestBackupImport:
    """备份导入测试。"""

    def test_导入备份(self):
        """应能从 tar.gz 文件导入数据。"""
        user, project = _create_user_and_project("carol", "Proj")

        # 先导出
        _, export_path = svc.export_backup(project["id"], user.id)

        # 再导入
        result = svc.import_backup(project["id"], user.id, export_path)
        assert "stats" in result
        assert result["project_id"] == project["id"]

    def test_非owner不能导入(self):
        """非 owner 不能导入备份。"""
        owner = register_user("owner1", "pw123")
        editor = register_user("editor1", "pw123")
        project = psvc.create_project("Proj", "", owner.id)
        psvc.add_member(project["id"], owner.id, editor.id, "editor")

        _, export_path = svc.export_backup(project["id"], owner.id)

        with pytest.raises(PermissionError, match="仅有项目 owner"):
            svc.import_backup(project["id"], editor.id, export_path)


class TestSemanticLint:
    """语义 lint 测试。"""

    def test_空项目lint(self):
        """空项目的 lint 应返回无问题。"""
        user, project = _create_user_and_project("dave", "Proj")
        result = svc.run_semantic_lint(project["id"], user.id)
        # 新项目可能没有 wiki 目录
        assert "status" in result

    def test_检测断链(self):
        """有断链的页面应被检测到。"""
        user, project = _create_user_and_project("eve", "Proj")
        wiki = _wiki_dir(project["id"])
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "sources").mkdir(exist_ok=True)
        # 页面有断链指向不存在的页面
        atomic_write(wiki / "sources" / "Test.md", "# Test\n[[NonExistentPage]]")

        result = svc.run_semantic_lint(project["id"], user.id)
        assert result["issue_count"] >= 1
        broken = [i for i in result["issues"] if i["type"] == "broken_link"]
        assert len(broken) >= 1


class TestAuditLog:
    """审计日志测试。"""

    def test_查询审计日志(self):
        """应能查询审计日志。"""
        user, project = _create_user_and_project("frank", "Proj")

        # 先写入一些审计日志
        audit_db = get_db("audit")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        audit_db.execute(
            "INSERT INTO audit_log (timestamp, action, user_id, username, project_id, target, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, "test.action", user.id, user.username, project["id"], "test_target", "success"),
        )
        audit_db.commit()

        result = svc.get_audit_log(user.id, project_id=project["id"])
        assert result["total"] >= 1
        assert result["entries"][0]["action"] == "test.action"

    def test_按项目过滤审计日志(self):
        """按项目 ID 过滤应只返回该项目的日志。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        p1 = psvc.create_project("Proj1", "", u1.id)
        p2 = psvc.create_project("Proj2", "", u2.id)

        audit_db = get_db("audit")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        audit_db.execute(
            "INSERT INTO audit_log (timestamp, action, user_id, username, project_id, target, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, "action1", u1.id, u1.username, p1["id"], "t1", "success"),
        )
        audit_db.execute(
            "INSERT INTO audit_log (timestamp, action, user_id, username, project_id, target, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, "action2", u2.id, u2.username, p2["id"], "t2", "success"),
        )
        audit_db.commit()

        result = svc.get_audit_log(u1.id, project_id=p1["id"])
        assert result["total"] == 1
        assert result["entries"][0]["action"] == "action1"
