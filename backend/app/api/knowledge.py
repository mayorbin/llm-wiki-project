# backend/app/api/knowledge.py
"""知识 API 路由——LLM 查询、Wiki 页面 CRUD 和编辑历史。"""
import json
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_current_user
from app.services import query_service as svc

router = APIRouter()

# ── 请求模型 ──


class QueryRequest(BaseModel):
    """知识查询请求。"""
    project_id: str = Field(description="项目 ID")
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    model: Optional[str] = Field(default=None, description="LLM 模型（可选）")


class UpdatePageRequest(BaseModel):
    """更新页面请求。"""
    project_id: str = Field(description="项目 ID")
    content: str = Field(min_length=1, description="新的页面内容")


# ── LLM 查询 ──


@router.post("/knowledge/query")
async def query_knowledge(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
):
    """使用 LLM 查询知识库，自动引用 [[wikilinks]]。"""
    try:
        return svc.query_knowledge(body.project_id, user["id"], body.question, body.model)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 流式查询 ──


@router.get("/knowledge/query/stream")
async def query_knowledge_stream(
    project_id: str = Query(description="项目 ID"),
    question: str = Query(min_length=1, max_length=2000, description="用户问题"),
    model: Optional[str] = Query(default=None, description="LLM 模型（可选）"),
    user: dict = Depends(get_current_user),
):
    """流式查询知识库——通过 SSE 推送进度和逐 token 回答。"""
    async def event_generator():
        try:
            async for event in svc.query_knowledge_stream(
                project_id, user["id"], question, model,
            ):
                event_type = event["event"]
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except PermissionError as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── 页面目录树 ──


@router.get("/knowledge/pages")
async def get_page_tree(
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取 Wiki 页面的目录树结构。"""
    try:
        return svc.get_page_tree(project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 页面 CRUD ──


@router.get("/knowledge/pages/{page_path:path}")
async def get_page(
    page_path: str = Path(description="相对于 wiki/ 的页面路径"),
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """读取 Wiki 页面完整内容。"""
    try:
        return svc.get_page(project_id, user["id"], page_path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/knowledge/pages/{page_path:path}")
async def update_page(
    page_path: str = Path(description="相对于 wiki/ 的页面路径"),
    body: UpdatePageRequest = None,
    user: dict = Depends(get_current_user),
):
    """编辑 Wiki 页面内容（editor/owner 可操作）。"""
    try:
        return svc.update_page(body.project_id, user["id"], page_path, body.content)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 页面历史 ──


@router.get("/knowledge/pages/{page_path:path}/history")
async def get_page_history(
    page_path: str = Path(description="相对于 wiki/ 的页面路径"),
    project_id: str = Query(description="项目 ID"),
    user: dict = Depends(get_current_user),
):
    """获取页面的编辑历史。"""
    try:
        return svc.get_page_history(project_id, user["id"], page_path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
