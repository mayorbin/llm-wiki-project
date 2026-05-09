# backend/app/api/projects.py
"""项目 API 路由——项目 CRUD、成员管理、设置管理和健康检查。"""
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_current_user, get_project_context
from app.services import project_service as svc

router = APIRouter()

# ── 请求模型 ──


class CreateProjectRequest(BaseModel):
    """创建项目请求。"""
    name: str = Field(min_length=1, max_length=100, description="项目名称")
    description: str = Field(default="", max_length=500, description="项目描述")


class UpdateProjectRequest(BaseModel):
    """更新项目请求。"""
    name: Optional[str] = Field(default=None, max_length=100, description="新名称")
    description: Optional[str] = Field(default=None, max_length=500, description="新描述")


class AddMemberRequest(BaseModel):
    """添加成员请求。"""
    user_id: str = Field(description="目标用户 ID")
    role: str = Field(default="editor", description="角色: editor 或 viewer")


class TransferRequest(BaseModel):
    """转让所有权请求。"""
    new_owner_id: str = Field(description="接收所有权的用户 ID")


class UpdateSettingsRequest(BaseModel):
    """更新项目设置请求（部分更新）。"""
    settings: dict = Field(description="要更新的设置键值对")


# ── 项目 CRUD ──


@router.get("/projects")
async def list_projects(
    status: Optional[str] = Query(None, description="按状态过滤（active/archived）"),
    user: dict = Depends(get_current_user),
):
    """获取当前用户有权访问的所有项目。"""
    projects = svc.list_projects(user["id"], status=status)
    return {"projects": projects, "count": len(projects)}


@router.post("/projects")
async def create_project(
    body: CreateProjectRequest,
    user: dict = Depends(get_current_user),
):
    """创建新项目，当前用户自动成为 owner。"""
    try:
        result = svc.create_project(body.name, body.description, user["id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str = Path(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取项目详情（含当前用户在此项目中的角色）。"""
    try:
        return svc.get_project(project_id, user["id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str = Path(description="项目 ID"),
    body: UpdateProjectRequest = None,
    user: dict = Depends(get_current_user),
):
    """更新项目名称或描述（仅 owner 可操作）。"""
    try:
        return svc.update_project(
            project_id, user["id"],
            name=body.name if body else None,
            description=body.description if body else None,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str = Path(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """删除项目及其所有关联数据（仅 owner 可操作，不可逆）。"""
    try:
        svc.delete_project(project_id, user["id"])
        return {"detail": "项目已删除"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 成员管理 ──


@router.get("/projects/{project_id}/members")
async def list_members(
    project_id: str = Path(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取项目成员列表（任何成员可查看）。"""
    try:
        return {"members": svc.list_members(project_id, user["id"])}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/projects/{project_id}/members")
async def add_member(
    project_id: str = Path(description="项目 ID"),
    body: AddMemberRequest = None,
    user: dict = Depends(get_current_user),
):
    """添加成员到项目（仅 owner 可操作）。"""
    try:
        result = svc.add_member(project_id, user["id"], body.user_id, body.role)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}/members/{target_user_id}")
async def remove_member(
    project_id: str = Path(description="项目 ID"),
    target_user_id: str = Path(description="要移除的用户 ID"),
    user: dict = Depends(get_current_user),
):
    """从项目中移除成员（仅 owner 可操作）。"""
    try:
        svc.remove_member(project_id, user["id"], target_user_id)
        return {"detail": "成员已移除"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/transfer")
async def transfer_ownership(
    project_id: str = Path(description="项目 ID"),
    body: TransferRequest = None,
    user: dict = Depends(get_current_user),
):
    """转让项目所有权（仅 owner 可操作）。"""
    try:
        result = svc.transfer_ownership(project_id, user["id"], body.new_owner_id)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 项目设置 ──


@router.get("/projects/{project_id}/settings")
async def get_settings(
    project_id: str = Path(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取项目设置（任何成员可读）。"""
    try:
        return svc.get_project_settings(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/projects/{project_id}/settings")
async def update_settings(
    project_id: str = Path(description="项目 ID"),
    body: UpdateSettingsRequest = None,
    user: dict = Depends(get_current_user),
):
    """更新项目设置（owner/editor 可操作，部分更新）。"""
    try:
        return svc.update_project_settings(project_id, user["id"], body.settings)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 健康检查 ──


@router.get("/projects/{project_id}/health")
async def health_check(
    project_id: str = Path(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """执行项目健康检查。"""
    try:
        return svc.project_health_check(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
