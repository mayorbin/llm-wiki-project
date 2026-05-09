# backend/app/api/maintenance.py
"""维护 API 路由——备份导出/导入、语义 lint 和审计日志查询。"""
import os
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path

from app.api.deps import get_current_user
from app.services import backup_service as svc

router = APIRouter()

# ── 请求模型 ──


class ExportBackupRequest(BaseModel):
    """导出备份请求。"""
    project_id: str = Field(description="项目 ID")


class LintRequest(BaseModel):
    """语义 lint 请求。"""
    project_id: str = Field(description="项目 ID")


# ── 备份管理 ──


@router.post("/backup/export")
async def export_backup(
    body: ExportBackupRequest,
    user: dict = Depends(get_current_user),
):
    """导出项目数据为 tar.gz 压缩包。"""
    try:
        export_name, export_path = svc.export_backup(body.project_id, user["id"])
        return FileResponse(
            path=str(export_path),
            filename=export_name,
            media_type="application/gzip",
            background=None,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/backup/import")
async def import_backup(
    file: UploadFile = File(description="备份 tar.gz 文件"),
    project_id: str = Form(description="目标项目 ID"),
    user: dict = Depends(get_current_user),
):
    """从 tar.gz 备份文件导入项目数据（覆盖现有数据）。"""
    # 保存上传的临时文件
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        result = svc.import_backup(project_id, user["id"], tmp_path)

        # 清理临时文件
        tmp_path.unlink(missing_ok=True)

        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# ── 语义 Lint ──


@router.post("/lint")
async def run_lint(
    body: LintRequest,
    user: dict = Depends(get_current_user),
):
    """运行语义 lint 检查（断链、空页面等）。"""
    try:
        return svc.run_semantic_lint(body.project_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 审计日志 ──


@router.get("/audit-log")
async def get_audit_log(
    project_id: Optional[str] = Query(default=None, description="按项目过滤"),
    action: Optional[str] = Query(default=None, description="按操作类型过滤"),
    offset: int = Query(default=0, ge=0, description="分页偏移"),
    limit: int = Query(default=50, ge=1, le=200, description="每页数量"),
    user: dict = Depends(get_current_user),
):
    """查询审计日志（分页）。"""
    try:
        return svc.get_audit_log(
            user["id"],
            project_id=project_id,
            action=action,
            offset=offset,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
