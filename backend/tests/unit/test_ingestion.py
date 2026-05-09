# backend/tests/unit/test_ingestion.py
"""摄入服务测试。"""
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.auth_service import register_user
from app.services import project_service as psvc
from app.services import ingest_service as svc


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


class TestTriggerIngestion:
    """触发摄入测试。"""

    def test_触发摄入任务成功(self):
        """触发摄入应创建任务并返回 task_id。"""
        user, project = _create_user_and_project("alice", "Proj")
        result = svc.trigger_ingestion(
            project["id"], user.id, user.username,
            ["doc1.md", "doc2.md"],
        )

        assert result["status"] == "queued"
        assert result["task_id"].startswith("task_")
        assert result["file_count"] == 2

    def test_空文件列表触发失败(self):
        """空文件列表必须拒绝。"""
        user, project = _create_user_and_project("bob", "Proj")
        with pytest.raises(ValueError, match="不能为空"):
            svc.trigger_ingestion(project["id"], user.id, user.username, [])

    def test_无权访问项目时拒绝(self):
        """未加入项目的用户不能触发摄入。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        project = psvc.create_project("Proj", "", u1.id)

        with pytest.raises(PermissionError):
            svc.trigger_ingestion(project["id"], u2.id, u2.username, ["doc.md"])


class TestTaskStatus:
    """任务状态查询测试。"""

    def test_查询任务状态(self):
        """创建任务后应能查询其状态。"""
        user, project = _create_user_and_project("carol", "Proj")
        result = svc.trigger_ingestion(
            project["id"], user.id, user.username, ["doc.md"],
        )

        status = svc.get_task_status(project["id"], result["task_id"], user.id)
        assert status["status"] == "queued"
        assert status["task_id"] == result["task_id"]

    def test_不存在的任务返回错误(self):
        """查询不存在的任务应抛出 ValueError。"""
        user, project = _create_user_and_project("dave", "Proj")
        with pytest.raises(ValueError, match="不存在"):
            svc.get_task_status(project["id"], "task_nonexistent", user.id)

    def test_批量状态查询(self):
        """批量查询多个任务的状态。"""
        user, project = _create_user_and_project("eve", "Proj")
        t1 = svc.trigger_ingestion(project["id"], user.id, user.username, ["a.md"])
        t2 = svc.trigger_ingestion(project["id"], user.id, user.username, ["b.md"])

        result = svc.batch_get_statuses(project["id"], [t1["task_id"], t2["task_id"], "fake_id"], user.id)
        assert len(result["statuses"]) == 3
        assert result["statuses"][t1["task_id"]]["status"] == "queued"
        assert result["statuses"]["fake_id"]["status"] == "not_found"


class TestTaskHistory:
    """任务历史测试。"""

    def test_分页查询历史(self):
        """应能分页查询任务历史。"""
        user, project = _create_user_and_project("frank", "Proj")
        for i in range(3):
            svc.trigger_ingestion(project["id"], user.id, user.username, [f"doc{i}.md"])

        history = svc.get_task_history(project["id"], user.id, limit=2)
        assert len(history["tasks"]) == 2
        assert history["total"] == 3

    def test_按状态过滤历史(self):
        """应按状态过滤任务历史。"""
        user, project = _create_user_and_project("george", "Proj")
        svc.trigger_ingestion(project["id"], user.id, user.username, ["doc.md"])

        # 过滤 queued 状态
        history = svc.get_task_history(project["id"], user.id, status="queued")
        assert history["total"] >= 1

        # 过滤不存在的状态
        history2 = svc.get_task_history(project["id"], user.id, status="completed")
        assert history2["total"] == 0


class TestTaskRetry:
    """任务重试测试。"""

    def test_重试失败任务(self):
        """失败的任务应可重试。"""
        user, project = _create_user_and_project("henry", "Proj")
        result = svc.trigger_ingestion(project["id"], user.id, user.username, ["doc.md"])

        # 手动标记为失败
        from app.storage.database import get_db
        db = get_db("tasks")
        db.execute(
            "UPDATE task_queue SET status = 'failed', error_message = 'test error' WHERE task_id = ?",
            (result["task_id"],),
        )
        db.commit()

        retry_result = svc.retry_task(project["id"], result["task_id"], user.id, user.username)
        assert retry_result["status"] == "queued"

    def test_不能重试运行中的任务(self):
        """运行中的任务不可重试。"""
        user, project = _create_user_and_project("iris", "Proj")
        result = svc.trigger_ingestion(project["id"], user.id, user.username, ["doc.md"])

        from app.storage.database import get_db
        db = get_db("tasks")
        db.execute("UPDATE task_queue SET status = 'running' WHERE task_id = ?",
                    (result["task_id"],))
        db.commit()

        with pytest.raises(ValueError, match="只有失败或已完成"):
            svc.retry_task(project["id"], result["task_id"], user.id, user.username)
