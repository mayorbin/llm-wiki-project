# backend/app/services/audit_service.py
"""审计日志服务——双重存储（SQLite + wiki/log.md）。"""
import json
import logging
from datetime import datetime, timezone
from app.storage.database import get_db

logger = logging.getLogger(__name__)


def write_audit_log(action: str, user_id: str, username: str, project_id: str, target: str, result: str = "success", detail: dict = None, error: str = None):
    """写入审计日志——SQLite（结构化） + wiki/log.md（可读）。"""
    db = get_db("audit")
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""INSERT INTO audit_log (timestamp, action, user_id, username, project_id, target, detail, result, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now, action, user_id, username, project_id, target, json.dumps(detail) if detail else None, result, error))
    db.commit()


def query_audit_log(project_id: str, cursor: str = None, limit: int = 50, action: str = None, user_id: str = None) -> dict:
    """查询项目审计日志（cursor-based 分页）。"""
    db = get_db("audit")
    sql = "SELECT * FROM audit_log WHERE project_id = ?"
    params = [project_id]
    if action:
        sql += " AND action = ?"
        params.append(action)
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit + 1)

    rows = db.execute(sql, params).fetchall()
    has_more = len(rows) > limit
    data = [dict(r) for r in rows[:limit]]
    next_cursor = data[-1]["id"] if has_more and data else None

    return {"data": data, "pagination": {"strategy": "cursor", "limit": limit, "has_more": has_more, "next_cursor": str(next_cursor) if next_cursor else None}}
