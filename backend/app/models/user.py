# backend/app/models/user.py
"""用户和项目相关的 Pydantic 数据模型。"""
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """注册/创建用户请求。"""
    username: str = Field(min_length=2, max_length=50, description="登录用户名")
    password: str = Field(min_length=6, max_length=128, description="明文密码")
    display_name: str = Field(default="", max_length=100, description="显示名称")


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token 对响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class RefreshRequest(BaseModel):
    """刷新 Token 请求。"""
    refresh_token: str


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: str
    username: str
    display_name: str
    role: str         # admin | user
    is_admin: bool
    is_active: bool
    created_at: str
