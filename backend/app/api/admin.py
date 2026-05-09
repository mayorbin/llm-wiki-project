# backend/app/api/admin.py
"""全局管理 API——仅 admin 角色可访问。"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from app.api.deps import get_current_user
from app.storage.database import get_db
from app.services.auth_service import hash_password

router = APIRouter()


def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


@router.get("/users")
async def list_users(include_deleted: bool = False, admin: dict = Depends(require_admin)):
    db = get_db("users")
    sql = "SELECT id, username, display_name, role, is_active, deleted_at, created_at, last_login FROM users"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    rows = db.execute(sql + " ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/users")
async def create_user(username: str, password: str, display_name: str = "", role: str = "user", admin: dict = Depends(require_admin)):
    db = get_db("users")
    uid = f"u_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.execute("INSERT INTO users (id, username, password_hash, display_name, role, created_at) VALUES (?,?,?,?,?,?)",
            (uid, username, hash_password(password), display_name, role, now))
        db.commit()
        return {"id": uid, "username": username}
    except Exception as e:
        raise HTTPException(409, f"用户名已存在: {e}")


@router.patch("/users/{user_id}")
async def update_user(user_id: str, is_active: bool = None, role: str = None, admin: dict = Depends(require_admin)):
    db = get_db("users")
    if is_active is not None:
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
    if role:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def soft_delete_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_db("users")
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE users SET deleted_at = ?, is_active = 0 WHERE id = ?", (now, user_id))
    db.execute("DELETE FROM project_members WHERE user_id = ?", (user_id,))
    db.commit()
    return {"status": "deleted"}


@router.get("/projects")
async def list_all_projects(admin: dict = Depends(require_admin)):
    db = get_db("users")
    rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/takeover")
async def takeover_project(project_id: str, admin: dict = Depends(require_admin)):
    db = get_db("users")
    db.execute("INSERT OR REPLACE INTO project_members (project_id, user_id, role, joined_at) VALUES (?,?, 'owner', ?)",
        (project_id, admin["id"], datetime.now(timezone.utc).isoformat()))
    db.execute("UPDATE projects SET status = 'active' WHERE id = ?", (project_id,))
    db.commit()
    return {"status": "ok"}
