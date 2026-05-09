# backend/app/api/ingestion.py
"""摄入 API 路由——触发摄入、状态查询、重试和回滚。"""
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_current_user
from app.services import ingest_service as svc

router = APIRouter()

# ── 请求模型 ──


class TriggerIngestionRequest(BaseModel):
    """触发摄入请求。"""
    project_id: str = Field(description="项目 ID")
    file_paths: list[str] = Field(min_length=1, description="要摄入的文件路径列表")
    action: str = Field(default="ingest", description="操作类型: ingest 或 reingest")


class BatchStatusRequest(BaseModel):
    """批量状态查询请求。"""
    project_id: str = Field(description="项目 ID")
    task_ids: list[str] = Field(min_length=1, max_length=100, description="任务 ID 列表")


# ── 触发摄入 ──


@router.post("/ingestion/trigger")
async def trigger_ingestion(
    body: TriggerIngestionRequest,
    user: dict = Depends(get_current_user),
):
    """触发单个或批量文件摄入任务。"""
    try:
        return svc.trigger_ingestion(
            body.project_id, user["id"], user["username"],
            body.file_paths, body.action,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ingestion/retry/{task_id}")
async def retry_task(
    task_id: str = Path(description="任务 ID"),
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """重试失败的摄入任务。"""
    try:
        return svc.retry_task(project_id, task_id, user["id"], user["username"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 状态查询 ──


@router.get("/ingestion/status/{task_id}")
async def get_task_status(
    task_id: str = Path(description="任务 ID"),
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """查询单个摄入任务的进度和状态。"""
    try:
        return svc.get_task_status(project_id, task_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ingestion/statuses")
async def batch_get_statuses(
    body: BatchStatusRequest,
    user: dict = Depends(get_current_user),
):
    """批量查询多个任务的状态。"""
    try:
        return svc.batch_get_statuses(body.project_id, body.task_ids, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/ingestion/history")
async def get_task_history(
    project_id: str = Query(description="项目 ID"),
    offset: int = Query(default=0, ge=0, description="分页偏移"),
    limit: int = Query(default=50, ge=1, le=200, description="每页数量"),
    status: Optional[str] = Query(default=None, description="按状态过滤"),
    user: dict = Depends(get_current_user),
):
    """查询项目摄入任务历史（分页）。"""
    try:
        return svc.get_task_history(project_id, user["id"], offset, limit, status)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 回滚 ──


@router.post("/ingestion/rollback/{task_id}")
async def rollback_task(
    task_id: str = Path(description="任务 ID"),
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """回滚已完成的摄入任务。"""
    try:
        return svc.rollback_task(project_id, task_id, user["id"], user["username"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
