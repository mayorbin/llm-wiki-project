# backend/app/api/files.py
"""文件 API 路由——目录管理、文件上传/下载/移动/删除、变更检测和刷新摄入。"""
import os
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_current_user
from app.services import file_service as svc

router = APIRouter()

# ── 请求模型 ──


class MoveRequest(BaseModel):
    """移动文件请求。"""
    source: str = Field(description="源文件路径（相对 raw/）")
    destination_dir: str = Field(description="目标子目录（相对 raw/）")


class DetectChangesRequest(BaseModel):
    """变更检测请求。"""
    project_id: str = Field(description="项目 ID")


class RefreshRequest(BaseModel):
    """刷新摄入请求。"""
    project_id: str = Field(description="项目 ID")
    file_paths: list[str] = Field(description="要重新摄入的文件路径列表")


class RefreshAllRequest(BaseModel):
    """刷新所有变更请求。"""
    project_id: str = Field(description="项目 ID")


class DirRequest(BaseModel):
    """目录操作请求。"""
    project_id: str = Field(description="项目 ID")
    path: str = Field(default="", description="相对于 raw/ 的子目录路径")


class DeleteDirRequest(BaseModel):
    """删除目录请求。"""
    project_id: str = Field(description="项目 ID")
    path: str = Field(description="相对于 raw/ 的子目录路径")


# ── 目录管理 ──


@router.get("/files/dirs")
async def list_directories(
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取 raw/ 目录树。"""
    try:
        return svc.list_directory_tree(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/files/dirs")
async def create_directory(
    body: DirRequest,
    user: dict = Depends(get_current_user),
):
    """在 raw/ 下创建子目录。"""
    try:
        svc.create_directory(body.project_id, user["id"], body.path)
        return {"detail": "目录创建成功", "path": body.path}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/files/dirs")
async def delete_directory(
    body: DeleteDirRequest,
    user: dict = Depends(get_current_user),
):
    """删除 raw/ 下的空子目录。"""
    try:
        svc.delete_directory(body.project_id, user["id"], body.path)
        return {"detail": "目录已删除", "path": body.path}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 文件上传 ──


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(description="要上传的文件"),
    project_id: str = Form(description="项目 ID"),
    subdir: str = Form(default="", description="子目录路径（可选）"),
    user: dict = Depends(get_current_user),
):
    """上传单个文件到 raw/ 目录。"""
    try:
        result = svc.upload_file(project_id, user["id"], file.file, file.filename, subdir)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/files/upload-batch")
async def upload_batch(
    files: list[UploadFile] = File(description="要上传的文件列表"),
    project_id: str = Form(description="项目 ID"),
    subdir: str = Form(default="", description="子目录路径（可选）"),
    user: dict = Depends(get_current_user),
):
    """批量上传文件到 raw/ 目录。"""
    try:
        file_tuples = [(f.file, f.filename) for f in files]
        result = svc.upload_batch(project_id, user["id"], file_tuples, subdir)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 文件查询 ──


@router.get("/files")
async def list_files(
    project_id: str = Query(description="项目 ID"),
    subdir: str = Query(default="", description="子目录路径"),
    offset: int = Query(default=0, ge=0, description="分页偏移"),
    limit: int = Query(default=50, ge=1, le=200, description="每页数量"),
    user: dict = Depends(get_current_user),
):
    """列出 raw/ 目录下的文件（分页）。"""
    try:
        return svc.list_files(project_id, user["id"], subdir, offset, limit)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files/{file_id}")
async def get_file_detail(
    file_id: str,
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取文件详情。"""
    try:
        return svc.get_file_detail(project_id, user["id"], file_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """下载文件。"""
    try:
        content_type, file_path = svc.download_file(project_id, user["id"], file_id)
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type=content_type,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """删除文件（级联删除关联的摄入记录）。"""
    try:
        svc.delete_file(project_id, user["id"], file_id)
        return {"detail": "文件已删除"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/files/move")
async def move_file(
    body: MoveRequest,
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """移动文件到指定子目录。"""
    try:
        return svc.move_file(project_id, user["id"], body.source, body.destination_dir)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 变更检测与刷新 ──


@router.post("/files/detect-changes")
async def detect_changes(
    body: DetectChangesRequest,
    user: dict = Depends(get_current_user),
):
    """检测 raw/ 目录下的文件变更（SHA256 + mtime）。"""
    try:
        return svc.detect_changes(body.project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/files/refresh")
async def refresh_files(
    body: RefreshRequest,
    user: dict = Depends(get_current_user),
):
    """重新摄入指定的文件。"""
    try:
        return svc.refresh_files(body.project_id, user["id"], body.file_paths)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/files/refresh-all")
async def refresh_all(
    body: RefreshAllRequest,
    user: dict = Depends(get_current_user),
):
    """重新摄入所有检测到变更的文件。"""
    try:
        return svc.refresh_all_changed(body.project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
