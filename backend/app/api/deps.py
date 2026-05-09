# backend/app/api/deps.py
"""
FastAPI 依赖注入模块。

提供：
  - get_current_user: 从 Authorization header 提取 JWT 并返回用户信息
  - get_project_context: 校验用户在项目中的访问权限
"""

from fastapi import HTTPException, Header
from app.services.auth_service import decode_token
from app.storage.database import get_db


async def get_current_user(authorization: str = Header(...)) -> dict:
    """从 Bearer Token 提取当前用户信息。

    在所有需要认证的端点中通过 Depends(get_current_user) 注入。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证格式错误，应为 Bearer <token>")

    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效或已过期的 Token")

    return {
        "id": payload["sub"],
        "username": payload["username"],
        "role": payload["role"],
    }


def get_project_context(project_id: str, user: dict) -> dict:
    """获取当前用户在某项目中的上下文（角色 + 项目状态）。

    如果项目不存在或用户无权访问，抛出 404。
    如果项目已归档，在写操作端额外校验。
    """
    db = get_db("users")
    row = db.execute(
        """SELECT pm.role, p.status
           FROM project_members pm
           JOIN projects p ON p.id = pm.project_id
           WHERE pm.project_id = ? AND pm.user_id = ?""",
        (project_id, user["id"]),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")

    return {"project_id": project_id, "role": row["role"], "status": row["status"]}
