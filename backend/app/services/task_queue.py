# backend/app/services/task_queue.py
"""摄入任务队列——SQLite 持久化 + 内存调度。"""
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from app.storage.database import get_db

logger = logging.getLogger(__name__)

# 每项目的内存队列（SQLite 是真实数据源，内存是调度缓存）
_project_queues: dict[str, list] = {}


def create_task(project_id: str, action: str, file_paths: list[str], created_by: str) -> dict:
    """创建新任务——写入 SQLite + 加入内存队列。"""
    db = get_db("tasks")
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""INSERT INTO task_queue (task_id, project_id, action, file_paths, status, created_by, created_at)
        VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
        (task_id, project_id, action, json.dumps(file_paths), created_by, now))
    db.commit()

    task = {"task_id": task_id, "project_id": project_id, "action": action, "status": "queued", "progress": 0}
    if project_id not in _project_queues:
        _project_queues[project_id] = []
    _project_queues[project_id].append(task)

    logger.info("任务已创建", extra={"task_id": task_id, "action": action, "project_id": project_id})
    return task


def get_task_status(task_id: str) -> Optional[dict]:
    """查询任务状态——优先查内存，回退 SQLite。"""
    for queue in _project_queues.values():
        for task in queue:
            if task["task_id"] == task_id:
                return dict(task)
    db = get_db("tasks")
    row = db.execute("SELECT * FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def update_task_status(task_id: str, status: str, progress: int = 0, error_code: str = None, error_message: str = None):
    """更新任务状态——先写 SQLite，再更新内存。"""
    db = get_db("tasks")
    now = datetime.now(timezone.utc).isoformat()
    if status == "running":
        db.execute("UPDATE task_queue SET status=?, progress=?, started_at=? WHERE task_id=?",
            (status, progress, now, task_id))
    elif status in ("completed", "failed"):
        db.execute("UPDATE task_queue SET status=?, progress=?, error_code=?, error_message=?, completed_at=? WHERE task_id=?",
            (status, progress, error_code, error_message, now, task_id))
    else:
        db.execute("UPDATE task_queue SET status=?, progress=? WHERE task_id=?",
            (status, progress, task_id))
    db.commit()
    for queue in _project_queues.values():
        for task in queue:
            if task["task_id"] == task_id:
                task["status"] = status
                task["progress"] = progress


def get_next_queued(project_id: str) -> Optional[dict]:
    """获取项目队列中下一个待执行任务。"""
    if project_id not in _project_queues or not _project_queues[project_id]:
        return None
    for task in _project_queues[project_id]:
        if task["status"] == "queued":
            return task
    return None


async def recover_tasks_on_startup():
    """服务重启时恢复未完成任务。"""
    db = get_db("tasks")
    rows = db.execute("SELECT * FROM task_queue WHERE status IN ('queued', 'running') ORDER BY created_at").fetchall()
    for row in rows:
        task = dict(row)
        if task["status"] == "running":
            db.execute("UPDATE task_queue SET status='queued', progress=0, started_at=NULL WHERE task_id=?", (task["task_id"],))
            task["status"] = "queued"
            task["progress"] = 0
        if task["project_id"] not in _project_queues:
            _project_queues[task["project_id"]] = []
        _project_queues[task["project_id"]].append(task)
    db.commit()
    if rows:
        logger.info(f"启动恢复: {len(rows)} 个未完成任务已重新排队")


def cleanup_expired(max_age_days: int = 7):
    """清理过期的已完成/失败任务。"""
    db = get_db("tasks")
    cutoff = datetime.now(timezone.utc).isoformat()
    db.execute("DELETE FROM task_queue WHERE status IN ('completed','failed') AND completed_at < ?", (cutoff,))
    db.commit()
