# backend/app/services/project_service.py
"""
项目服务——项目的创建、查询、更新、删除、成员管理和设置管理。

项目状态流转：active → archived（不可逆，需通过管理员 API 删除）。
权限模型：
  - owner:     完全控制（删除、转让、管理成员）
  - editor:    读 + 写（创建/编辑知识页面）
  - viewer:    只读
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.storage.database import get_db
from app.storage.file_storage import safe_subdir

logger = logging.getLogger(__name__)

# ── 辅助函数 ──


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _validate_role(role: str):
    """校验角色是否为合法值。"""
    if role not in ("owner", "editor", "viewer"):
        raise ValueError(f"无效的角色: {role}，支持 owner/editor/viewer")


# ── 项目 CRUD ──


def list_projects(user_id: str, status: Optional[str] = None) -> list[dict]:
    """获取用户有权限访问的所有项目。

    Args:
        user_id: 当前用户 ID
        status: 可选的状态过滤（active/archived），为空则返回全部
    """
    db = get_db("users")
    query = """SELECT p.id, p.name, p.description, p.status, p.created_by, p.created_at, p.archived_at,
                      pm.role AS user_role
               FROM projects p
               JOIN project_members pm ON pm.project_id = p.id
               WHERE pm.user_id = ?
               ORDER BY p.created_at DESC"""
    params = [user_id]

    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def create_project(name: str, description: str, owner_id: str) -> dict:
    """创建新项目，创建者自动成为 owner。

    Args:
        name: 项目名称（1-100 字符）
        description: 项目描述
        owner_id: 创建者用户 ID
    """
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("项目名称长度为 1-100 字符")

    db = get_db("users")
    project_id = f"p_{uuid.uuid4().hex[:12]}"
    now = _now()

    db.execute(
        """INSERT INTO projects (id, name, description, status, created_by, created_at)
           VALUES (?, ?, ?, 'active', ?, ?)""",
        (project_id, name, description, owner_id, now),
    )

    # 创建者自动成为 owner
    db.execute(
        """INSERT INTO project_members (project_id, user_id, role, joined_at)
           VALUES (?, ?, 'owner', ?)""",
        (project_id, owner_id, now),
    )

    # 创建默认项目设置
    db.execute(
        """INSERT INTO project_settings (project_id, settings, updated_at)
           VALUES (?, '{}', ?)""",
        (project_id, now),
    )

    db.commit()

    logger.info("项目创建成功", extra={"project_id": project_id, "project_name": name, "owner": owner_id})

    return {
        "id": project_id, "name": name, "description": description,
        "status": "active", "created_by": owner_id, "created_at": now, "user_role": "owner",
    }


def get_project(project_id: str, user_id: str) -> dict:
    """获取项目详情（含当前用户角色和成员数统计）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID（必须是有权访问该项目的成员）

    Raises:
        ValueError: 项目不存在或用户无权访问
    """
    db = get_db("users")
    row = db.execute(
        """SELECT p.id, p.name, p.description, p.status, p.created_by, p.created_at, p.archived_at,
                  pm.role AS user_role,
                  (SELECT COUNT(*) FROM project_members WHERE project_id = p.id) AS member_count
           FROM projects p
           JOIN project_members pm ON pm.project_id = p.id
           WHERE p.id = ? AND pm.user_id = ?""",
        (project_id, user_id),
    ).fetchone()

    if not row:
        raise ValueError("项目不存在或无权访问")

    return dict(row)


def update_project(project_id: str, user_id: str, name: Optional[str] = None,
                   description: Optional[str] = None) -> dict:
    """更新项目名称或描述（仅 owner 可操作）。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        name: 新名称（可选）
        description: 新描述（可选）
    """
    db = get_db("users")

    # 权限校验
    role_row = db.execute(
        """SELECT role, p.status FROM project_members pm
           JOIN projects p ON p.id = pm.project_id
           WHERE pm.project_id = ? AND pm.user_id = ?""",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以修改项目信息")
    if role_row["status"] == "archived":
        raise PermissionError("已归档的项目不可修改")

    # 构建更新 SQL
    updates = []
    params = []
    if name is not None:
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("项目名称长度为 1-100 字符")
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if not updates:
        raise ValueError("没有需要更新的字段")

    params.append(project_id)
    db.execute(
        f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    db.commit()

    logger.info("项目更新成功", extra={"project_id": project_id, "updated_by": user_id})

    return get_project(project_id, user_id)


def delete_project(project_id: str, user_id: str):
    """删除项目（仅 owner 可操作，硬删除所有数据）。

    删除范围：
      - 项目记录
      - 成员关系
      - 项目设置
      - 摄入任务记录
      - 审计日志（mark delete）

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID（必须是 owner）
    """
    db = get_db("users")

    # 权限校验
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以删除项目")

    # 删除成员关系
    db.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
    # 删除项目设置
    db.execute("DELETE FROM project_settings WHERE project_id = ?", (project_id,))
    # 删除项目
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()

    # 删除关联的摄入任务
    tasks_db = get_db("tasks")
    tasks_db.execute("DELETE FROM task_queue WHERE project_id = ?", (project_id,))
    tasks_db.commit()

    # 标记审计日志中的项目为已删除
    audit_db = get_db("audit")
    audit_db.execute(
        "UPDATE audit_log SET detail = COALESCE(detail, '') || ' [项目已删除]' WHERE project_id = ?",
        (project_id,),
    )
    audit_db.commit()

    logger.info("项目已删除", extra={"project_id": project_id, "deleted_by": user_id})


# ── 成员管理 ──


def list_members(project_id: str, user_id: str) -> list[dict]:
    """获取项目成员列表（任何成员可查看）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    db = get_db("users")

    # 权限校验
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")

    rows = db.execute(
        """SELECT pm.user_id, pm.role, pm.joined_at, u.username, u.display_name
           FROM project_members pm
           JOIN users u ON u.id = pm.user_id
           WHERE pm.project_id = ?
           ORDER BY pm.joined_at ASC""",
        (project_id,),
    ).fetchall()

    return [dict(r) for r in rows]


def add_member(project_id: str, user_id: str, target_user_id: str, role: str = "editor") -> dict:
    """添加成员到项目（仅 owner 可操作）。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        target_user_id: 要添加的用户 ID
        role: 角色（editor 或 viewer）
    """
    _validate_role(role)
    if role == "owner":
        raise ValueError("不能直接添加 owner，请使用转移所有权功能")

    db = get_db("users")

    # 权限校验
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以添加成员")

    # 检查目标用户是否存在
    target = db.execute("SELECT id FROM users WHERE id = ? AND deleted_at IS NULL", (target_user_id,)).fetchone()
    if not target:
        raise ValueError("目标用户不存在")

    # 检查是否已是成员
    existing = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, target_user_id),
    ).fetchone()
    if existing:
        raise ValueError("该用户已是项目成员")

    now = _now()
    db.execute(
        "INSERT INTO project_members (project_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (project_id, target_user_id, role, now),
    )
    db.commit()

    logger.info("成员添加成功", extra={"project_id": project_id, "added_user": target_user_id, "role": role})
    return {"project_id": project_id, "user_id": target_user_id, "role": role, "joined_at": now}


def remove_member(project_id: str, user_id: str, target_user_id: str):
    """从项目中移除成员（仅 owner 可操作，不能移除自己）。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        target_user_id: 要移除的用户 ID
    """
    if target_user_id == user_id:
        raise ValueError("不能移除自己，如需退出项目请使用转让所有权功能")

    db = get_db("users")

    # 权限校验
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以移除成员")

    # 检查目标是否是 owner
    target = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, target_user_id),
    ).fetchone()

    if not target:
        raise ValueError("目标用户不是项目成员")
    if target["role"] == "owner":
        raise ValueError("不能直接移除 owner，请使用转让所有权功能")

    db.execute(
        "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, target_user_id),
    )
    db.commit()

    logger.info("成员移除成功", extra={"project_id": project_id, "removed_user": target_user_id})


def transfer_ownership(project_id: str, user_id: str, target_user_id: str) -> dict:
    """转让项目所有权（仅 owner 可操作）。

    操作后当前 owner 变为 editor，目标用户变为 owner。

    Args:
        project_id: 项目 ID
        user_id: 当前 owner 的用户 ID
        target_user_id: 接收所有权的用户 ID
    """
    db = get_db("users")

    # 权限校验
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以转让所有权")

    # 检查目标用户是否是项目成员
    target = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, target_user_id),
    ).fetchone()

    if not target:
        raise ValueError("目标用户不是项目成员，请先添加为成员")

    # 执行转让：当前 owner 降为 editor，目标提升为 owner
    db.execute(
        "UPDATE project_members SET role = 'editor' WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    db.execute(
        "UPDATE project_members SET role = 'owner' WHERE project_id = ? AND user_id = ?",
        (project_id, target_user_id),
    )
    db.commit()

    logger.info("所有权转让成功", extra={"project_id": project_id, "from": user_id, "to": target_user_id})

    return {
        "project_id": project_id,
        "previous_owner": user_id,
        "new_owner": target_user_id,
        "transferred_at": _now(),
    }


# ── 项目设置 ──


def get_project_settings(project_id: str, user_id: str) -> dict:
    """获取项目设置（任何成员可读）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    db = get_db("users")

    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")

    settings_row = db.execute(
        "SELECT settings, updated_at FROM project_settings WHERE project_id = ?",
        (project_id,),
    ).fetchone()

    if not settings_row:
        return {"project_id": project_id, "settings": {}, "updated_at": ""}

    return {
        "project_id": project_id,
        "settings": json.loads(settings_row["settings"]),
        "updated_at": settings_row["updated_at"],
    }


def update_project_settings(project_id: str, user_id: str, settings: dict) -> dict:
    """更新项目设置（仅 owner/editor 可操作）。

    采用合并策略：传入的键值合并到现有设置中，不会删除未提及的键。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        settings: 要更新的设置键值对（部分更新）
    """
    db = get_db("users")

    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if not role_row:
        raise PermissionError("项目不存在或无权访问")
    if role_row["role"] not in ("owner", "editor"):
        raise PermissionError("仅有 owner 或 editor 可以修改项目设置")

    # 读取当前设置，合并更新
    row = db.execute(
        "SELECT settings FROM project_settings WHERE project_id = ?",
        (project_id,),
    ).fetchone()

    current = json.loads(row["settings"]) if row else {}
    current.update(settings)
    now = _now()

    db.execute(
        """INSERT INTO project_settings (project_id, settings, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(project_id) DO UPDATE SET settings = excluded.settings, updated_at = excluded.updated_at""",
        (project_id, json.dumps(current, ensure_ascii=False), now),
    )
    db.commit()

    logger.info("项目设置更新成功", extra={"project_id": project_id, "updated_keys": list(settings.keys())})

    return {"project_id": project_id, "settings": current, "updated_at": now}


# ── 健康检查 ──


def project_health_check(project_id: str, user_id: str) -> dict:
    """执行项目健康检查。

    检查项：
      - 项目目录结构完整性
      - 成员状态
      - 摄入任务统计

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    from pathlib import Path

    db = get_db("users")

    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")

    checks = {}
    settings = get_settings()
    project_dir = Path(settings.data_dir) / "projects" / project_id

    # 检查目录结构
    wiki_dir = project_dir / "wiki"
    graph_dir = project_dir / "graph"
    raw_dir = project_dir / "raw"

    checks["wiki_directory"] = "ok" if wiki_dir.exists() else "missing"
    checks["graph_directory"] = "ok" if graph_dir.exists() else "missing"
    checks["raw_directory"] = "ok" if raw_dir.exists() else "missing"

    # 检查成员数
    member_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM project_members WHERE project_id = ?",
        (project_id,),
    ).fetchone()["cnt"]
    checks["member_count"] = member_count

    # 检查摄入任务
    tasks_db = get_db("tasks")
    pending = tasks_db.execute(
        "SELECT COUNT(*) AS cnt FROM task_queue WHERE project_id = ? AND status IN ('queued', 'running')",
        (project_id,),
    ).fetchone()["cnt"]
    failed = tasks_db.execute(
        "SELECT COUNT(*) AS cnt FROM task_queue WHERE project_id = ? AND status = 'failed'",
        (project_id,),
    ).fetchone()["cnt"]
    checks["pending_tasks"] = pending
    checks["failed_tasks"] = failed

    all_ok = all(
        v == "ok" for k, v in checks.items()
        if k in ("wiki_directory", "graph_directory", "raw_directory")
    )

    return {
        "project_id": project_id,
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "checked_at": _now(),
    }
