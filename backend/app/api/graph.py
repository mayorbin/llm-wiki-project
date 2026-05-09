# backend/app/api/graph.py
"""知识图谱 API 路由——图谱数据查询、构建和统计。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services import graph_service as svc

router = APIRouter()

# ── 请求模型 ──


class BuildGraphRequest(BaseModel):
    """构建图谱请求。"""
    project_id: str = Field(description="项目 ID")
    run_inference: bool = Field(default=False, description="是否执行 LLM 语义推断")


# ── 图谱数据 ──


@router.get("/graph/data")
async def get_graph_data(
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取已构建的知识图谱 JSON 数据（nodes + edges）。"""
    try:
        return svc.get_graph_data(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 构建图谱 ──


@router.post("/graph/build")
async def build_graph(
    body: BuildGraphRequest,
    user: dict = Depends(get_current_user),
):
    """触发知识图谱构建（耗时的 LLM 操作，同步执行）。"""
    try:
        return svc.build_graph(body.project_id, user["id"], body.run_inference)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图谱构建失败: {str(e)}")


# ── 统计 ──


@router.get("/graph/stats")
async def get_graph_stats(
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取知识图谱统计信息（不触发构建）。"""
    try:
        return svc.get_graph_stats(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
