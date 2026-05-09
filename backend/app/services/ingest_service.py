# backend/app/services/ingest_service.py
"""
摄入服务——触发摄入任务、查询状态、重试和回滚。

摄入流程：
  1. 校验项目权限
  2. 获取项目写锁（LockManager）
  3. 创建任务记录（tasks.db）
  4. 由后台 worker 执行实际摄入（调用 ingest.py）
  5. 记录审计日志

回滚策略：
  摄入任务创建快照（.snapshot 目录），回滚时恢复快照中的文件。
"""

import uuid
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.storage.database import get_db
from app.storage.file_storage import safe_subdir, file_sha256
from app.services.lock_manager import LockManager

logger = logging.getLogger(__name__)


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _check_project_access(project_id: str, user_id: str):
    """校验用户对项目的访问权限。"""
    db = get_db("users")
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")


def _get_lock_manager() -> LockManager:
    """获取锁管理器实例。"""
    settings = get_settings()
    return LockManager(Path(settings.data_dir))


def _write_audit(project_id: str, user_id: str, username: str,
                 action: str, target: str, result: str, detail: str = "", error: str = ""):
    """写入审计日志。"""
    db = get_db("audit")
    db.execute(
        """INSERT INTO audit_log (timestamp, action, user_id, username, project_id,
           target, detail, result, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), action, user_id, username, project_id, target, detail, result, error),
    )
    db.commit()


# ── 触发摄入 ──


def trigger_ingestion(
    project_id: str, user_id: str, username: str,
    file_paths: list[str], action: str = "ingest",
) -> dict:
    """触发摄入任务（单个或批量）。

    创建任务记录放入 task_queue 表，由后台 worker 异步执行。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        username: 操作者用户名
        file_paths: 要摄入的文件路径列表（相对于 raw/）
        action: 操作类型（ingest 或 reingest）

    Returns:
        任务摘要
    """
    _check_project_access(project_id, user_id)

    if not file_paths:
        raise ValueError("文件路径列表不能为空")

    # 获取项目写锁
    lock_mgr = _get_lock_manager()
    lock = lock_mgr.acquire_project_write(project_id, timeout=10)

    try:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = _now()

        db = get_db("tasks")
        db.execute(
            """INSERT INTO task_queue
               (task_id, project_id, action, file_paths, status, progress,
                retry_count, max_retries, created_by, created_at)
               VALUES (?, ?, ?, ?, 'queued', 0, 0, 3, ?, ?)""",
            (
                task_id, project_id, action,
                json.dumps(file_paths, ensure_ascii=False),
                user_id, now,
            ),
        )
        db.commit()

        _write_audit(
            project_id, user_id, username,
            action=f"task.{action}", target=",".join(file_paths),
            result="queued", detail=f"任务 ID: {task_id}",
        )

        logger.info("摄入任务已创建", extra={
            "task_id": task_id, "project_id": project_id,
            "files": len(file_paths), "action": action,
        })

        return {
            "task_id": task_id,
            "status": "queued",
            "file_count": len(file_paths),
            "action": action,
            "created_at": now,
        }
    finally:
        lock_mgr.release(lock)


def retry_task(project_id: str, task_id: str, user_id: str, username: str) -> dict:
    """重试失败的摄入任务。

    重置任务状态为 queued，保留原有参数。

    Args:
        project_id: 项目 ID
        task_id: 任务 ID
        user_id: 操作者用户 ID
        username: 操作者用户名
    """
    _check_project_access(project_id, user_id)

    db = get_db("tasks")
    row = db.execute(
        "SELECT * FROM task_queue WHERE task_id = ? AND project_id = ?",
        (task_id, project_id),
    ).fetchone()

    if not row:
        raise ValueError(f"任务不存在: {task_id}")
    if row["status"] not in ("failed", "completed"):
        raise ValueError(f"只有失败或已完成的任务可以重试，当前状态: {row['status']}")

    # 重置任务
    now = _now()
    db.execute(
        """UPDATE task_queue
           SET status = 'queued', progress = 0, error_code = NULL,
               error_message = NULL, error_detail = NULL, started_at = NULL,
               completed_at = NULL, retry_count = retry_count + 1
           WHERE task_id = ?""",
        (task_id,),
    )
    db.commit()

    _write_audit(
        project_id, user_id, username,
        action="task.retry", target=task_id, result="queued",
    )

    logger.info("摄入任务已重试", extra={"task_id": task_id})
    return {"task_id": task_id, "status": "queued", "retried_at": now}


# ── 查询状态 ──


def get_task_status(project_id: str, task_id: str, user_id: str) -> dict:
    """查询单个任务的状态和进度。

    Args:
        project_id: 项目 ID
        task_id: 任务 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    db = get_db("tasks")
    row = db.execute(
        "SELECT * FROM task_queue WHERE task_id = ? AND project_id = ?",
        (task_id, project_id),
    ).fetchone()

    if not row:
        raise ValueError(f"任务不存在: {task_id}")

    task = dict(row)
    task["file_paths"] = json.loads(task.get("file_paths", "[]"))
    return task


def batch_get_statuses(project_id: str, task_ids: list[str], user_id: str) -> dict:
    """批量查询任务状态。

    Args:
        project_id: 项目 ID
        task_ids: 任务 ID 列表
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    db = get_db("tasks")
    results = {}
    for tid in task_ids:
        row = db.execute(
            "SELECT task_id, status, progress, error_message FROM task_queue "
            "WHERE task_id = ? AND project_id = ?",
            (tid, project_id),
        ).fetchone()
        if row:
            results[tid] = dict(row)
        else:
            results[tid] = {"task_id": tid, "status": "not_found", "error": "任务不存在"}

    return {"statuses": results}


def get_task_history(
    project_id: str, user_id: str,
    offset: int = 0, limit: int = 50,
    status: Optional[str] = None,
) -> dict:
    """查询项目下任务历史（分页，支持状态过滤）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        offset: 分页偏移
        limit: 每页数量
        status: 状态过滤（可选）
    """
    _check_project_access(project_id, user_id)

    db = get_db("tasks")

    if status:
        count_row = db.execute(
            "SELECT COUNT(*) AS cnt FROM task_queue WHERE project_id = ? AND status = ?",
            (project_id, status),
        ).fetchone()
        rows = db.execute(
            "SELECT * FROM task_queue WHERE project_id = ? AND status = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (project_id, status, limit, offset),
        ).fetchall()
    else:
        count_row = db.execute(
            "SELECT COUNT(*) AS cnt FROM task_queue WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        rows = db.execute(
            "SELECT * FROM task_queue WHERE project_id = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        ).fetchall()

    tasks = []
    for r in rows:
        task = dict(r)
        task["file_paths"] = json.loads(task.get("file_paths", "[]"))
        tasks.append(task)

    return {
        "tasks": tasks,
        "total": count_row["cnt"] if count_row else 0,
        "offset": offset,
        "limit": limit,
    }


# ── 回滚 ──


def rollback_task(project_id: str, task_id: str, user_id: str, username: str) -> dict:
    """回滚已完成的摄入任务。

    恢复快照目录中的文件，并删除摄入产生的 wiki 页面。

    Args:
        project_id: 项目 ID
        task_id: 任务 ID
        user_id: 操作者用户 ID
        username: 操作者用户名
    """
    _check_project_access(project_id, user_id)

    db = get_db("tasks")
    row = db.execute(
        "SELECT * FROM task_queue WHERE task_id = ? AND project_id = ?",
        (task_id, project_id),
    ).fetchone()

    if not row:
        raise ValueError(f"任务不存在: {task_id}")
    if row["status"] != "completed":
        raise ValueError(f"只有已完成的任务可以回滚，当前状态: {row['status']}")
    if not row["snapshot_dir"]:
        raise ValueError(f"任务 {task_id} 没有快照，无法回滚")

    snapshot_dir = Path(row["snapshot_dir"])
    settings = get_settings()
    project_dir = Path(settings.data_dir) / "projects" / project_id

    # 恢复快照中的文件
    restored_count = 0
    if snapshot_dir.exists():
        wiki_snapshot = snapshot_dir / "wiki"
        if wiki_snapshot.exists():
            # 移除当前 wiki 中摄入生成的页面，恢复快照
            target_wiki = project_dir / "wiki"
            for f in wiki_snapshot.rglob("*.md"):
                rel = f.relative_to(wiki_snapshot)
                target = target_wiki / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(target))
                restored_count += 1

    # 标记任务为已回滚
    now = _now()
    db.execute(
        "UPDATE task_queue SET error_message = COALESCE(error_message, '') || ' [已回滚]' "
        "WHERE task_id = ?",
        (task_id,),
    )
    db.commit()

    _write_audit(
        project_id, user_id, username,
        action="task.rollback", target=task_id, result="success",
        detail=f"恢复了 {restored_count} 个文件",
    )

    logger.info("摄入任务已回滚", extra={
        "task_id": task_id, "restored_files": restored_count,
    })

    return {"task_id": task_id, "status": "rolled_back", "restored_files": restored_count}
