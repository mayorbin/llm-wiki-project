# backend/app/api/auth.py
"""
认证 API 路由。
"""
from fastapi import APIRouter, HTTPException, Depends
from app.config import get_settings
from app.models.user import LoginRequest, RefreshRequest, UserCreate, TokenResponse
from app.services import auth_service
from app.storage.database import get_db
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """用户登录，返回 access_token + refresh_token。"""
    try:
        return auth_service.login(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    """使用 refresh_token 换取新的 Token 对（滚动刷新机制）。"""
    try:
        return auth_service.refresh_access_token(req.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/register")
async def register(req: UserCreate):
    """注册新用户（registration_open=false 时拒绝）。"""
    if not get_settings().registration_open:
        raise HTTPException(status_code=403, detail="注册功能已关闭，请联系管理员创建账号")
    try:
        return auth_service.register_user(req.username, req.password, req.display_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息和所属项目列表。

    前端应用初始化时调用，一次请求完成导航数据加载。
    """
    projects = auth_service.get_user_projects(user["id"])
    db = get_db("users")
    row = db.execute("SELECT display_name FROM users WHERE id = ?", (user["id"],)).fetchone()
    display_name = row["display_name"] if row else ""

    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": display_name,
            "role": user["role"],
            "is_admin": user["role"] == "admin",
        },
        "projects": projects,
    }


@router.post("/auth/logout")
async def logout(req: RefreshRequest):
    """登出——撤销 refresh_token。"""
    auth_service.logout(req.refresh_token)
    return {"status": "ok"}
