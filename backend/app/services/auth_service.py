# backend/app/services/auth_service.py
"""
认证服务——注册、登录、Token 签发与刷新。

JWT 设计：
  - access_token:  24h，负载含 user_id + username + role + type:"access"
  - refresh_token: 7d， 负载含 user_id + type:"refresh"（不含敏感信息）
  - 签名算法 HS256，密钥为 LLM_WIKI_SECRET_KEY

用户注销采用软删除（deleted_at 字段），不物理删除数据。
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from app.config import get_settings
from app.models.user import UserResponse, TokenResponse
from app.storage.database import get_db

logger = logging.getLogger(__name__)

# Token 黑名单（内存，存 refresh_token 的 jti，服务重启清空）
_token_blacklist: set[str] = set()


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, username: str, role: str) -> str:
    """签发短期 access_token（24h）。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_expire_hours),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    """签发长期 refresh_token（7d），仅用于刷新，不含用户敏感信息。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT，返回负载字典。验证失败返回 None。"""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        return None


def register_user(username: str, password: str, display_name: str = "") -> UserResponse:
    """注册新用户，返回用户信息。用户名重复时抛出 ValueError。"""
    db = get_db("users")
    user_id = f"u_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    try:
        db.execute(
            """INSERT INTO users (id, username, password_hash, display_name, role, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, hash_password(password), display_name, "user", now),
        )
        db.commit()
    except Exception as e:
        if "UNIQUE" in str(e).upper():
            raise ValueError(f"用户名 {username} 已存在") from e
        raise

    logger.info("用户注册成功", extra={"user_id": user_id, "username": username})
    return UserResponse(
        id=user_id, username=username, display_name=display_name,
        role="user", is_admin=False, is_active=True, created_at=now,
    )


def login(username: str, password: str) -> TokenResponse:
    """验证用户凭据，签发 Token 对。"""
    db = get_db("users")
    row = db.execute(
        "SELECT id, username, password_hash, role, is_active, deleted_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()

    if not row:
        raise ValueError("用户名或密码错误")
    if not verify_password(password, row["password_hash"]):
        raise ValueError("用户名或密码错误")
    if not row["is_active"] or row["deleted_at"]:
        raise ValueError("账号已被禁用或注销")

    # 更新最后登录时间
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"]))
    db.commit()

    logger.info("用户登录成功", extra={"user_id": row["id"], "username": row["username"]})
    return TokenResponse(
        access_token=create_access_token(row["id"], row["username"], row["role"]),
        refresh_token=create_refresh_token(row["id"]),
        expires_in=get_settings().access_token_expire_hours * 3600,
    )


def refresh_access_token(refresh_token: str) -> TokenResponse:
    """使用 refresh_token 换取新 Token 对（滚动刷新，旧 token 即时失效）。"""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("无效的 refresh_token")

    # 黑名单检查（防重放攻击）
    if payload.get("jti") in _token_blacklist:
        raise ValueError("Token 已被撤销")

    user_id = payload["sub"]
    db = get_db("users")
    row = db.execute(
        "SELECT id, username, role, is_active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not row or not row["is_active"]:
        raise ValueError("用户不存在或已禁用")

    # 旧 refresh_token 加入黑名单
    _token_blacklist.add(payload["jti"])

    return TokenResponse(
        access_token=create_access_token(row["id"], row["username"], row["role"]),
        refresh_token=create_refresh_token(row["id"]),
        expires_in=get_settings().access_token_expire_hours * 3600,
    )


def logout(refresh_token: str):
    """登出——将 refresh_token 加入内存黑名单。"""
    payload = decode_token(refresh_token)
    if payload:
        _token_blacklist.add(payload["jti"])
        logger.info("用户登出", extra={"user_id": payload["sub"]})


def get_user_projects(user_id: str) -> list[dict]:
    """获取用户所属项目列表（含每个项目的角色）。"""
    db = get_db("users")
    rows = db.execute(
        """SELECT p.id, p.name, pm.role, p.status
           FROM project_members pm
           JOIN projects p ON p.id = pm.project_id
           WHERE pm.user_id = ?
           ORDER BY p.created_at DESC""",
        (user_id,),
    ).fetchall()

    return [
        {"id": r["id"], "name": r["name"], "role": r["role"], "status": r["status"]}
        for r in rows
    ]


def get_user_by_id(user_id: str) -> Optional[dict]:
    """按 ID 查询用户。"""
    db = get_db("users")
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
