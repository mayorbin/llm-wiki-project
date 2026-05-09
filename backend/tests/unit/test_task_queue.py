# backend/tests/unit/test_task_queue.py
"""任务队列持久化测试。"""
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.task_queue import create_task, get_task_status, update_task_status


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-key-32chars-long-enough!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


def test_创建任务():
    task = create_task("proj-1", "ingest", ["file1.pdf"], "user-1")
    assert task["status"] == "queued"
    assert task["project_id"] == "proj-1"


def test_查询任务状态():
    task = create_task("proj-1", "ingest", ["doc.md"], "user-1")
    status = get_task_status(task["task_id"])
    assert status["status"] == "queued"


def test_更新任务状态():
    task = create_task("proj-1", "ingest", ["doc.md"], "user-1")
    update_task_status(task["task_id"], "running", progress=50)
    status = get_task_status(task["task_id"])
    assert status["status"] == "running"
    assert status["progress"] == 50


def test_完成任务():
    task = create_task("proj-1", "ingest", ["doc.md"], "user-1")
    update_task_status(task["task_id"], "completed", progress=100)
    status = get_task_status(task["task_id"])
    assert status["status"] == "completed"
