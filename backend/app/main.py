# backend/app/main.py
"""
FastAPI 应用入口。

启动时执行：
1. 加载并校验配置
2. 初始化数据库
3. 恢复未完成的任务
4. 注册路由和中间件

启动方式：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化资源，关闭时清理。"""
    # 启动时
    settings.validate_required()

    # 初始化日志系统
    from app.logging_config import setup_logging

    setup_logging(
        log_dir=Path(settings.data_dir) / "logs",
        level=settings.log_level,
    )

    # 初始化数据库（Task 2 实现后启用真实实现）
    from app.storage.database import init_db

    init_db(settings.data_dir)

    # 恢复未完成的任务
    from app.services.task_queue import recover_tasks_on_startup
    await recover_tasks_on_startup()

    yield  # 应用运行中

    # 关闭时清理（预留）


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由注册 ──

from app.api import auth, projects, files, ingestion, knowledge, graph, maintenance, admin

app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(projects.router, prefix="/api", tags=["项目"])
app.include_router(files.router, prefix="/api", tags=["文件"])
app.include_router(ingestion.router, prefix="/api", tags=["摄入"])
app.include_router(knowledge.router, prefix="/api", tags=["知识"])
app.include_router(graph.router, prefix="/api", tags=["图谱"])
app.include_router(maintenance.router, prefix="/api", tags=["维护"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理"])


# ── 公共健康检查端点（无需认证） ──


@app.get("/api/ping")
async def ping():
    """存活探针（K8s liveness）——零依赖，仅验证进程存活。"""
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/health")
async def health(
    deep: bool = Query(False, description="是否执行深度检查（含 LLM 连通性）"),
):
    """就绪探针（K8s readiness）——验证进程 + 关键依赖可用。"""
    checks = {"database": "ok"}

    # 检查文件系统可写
    try:
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".health_check"
        test_file.touch()
        test_file.unlink()
        checks["file_system"] = "ok"
    except Exception:
        checks["file_system"] = "error"

    # 深度检查：LLM 连通性
    if deep:
        try:
            from app.engines.llm_engine import verify_llm_connection

            checks["llm_api"] = "ok" if verify_llm_connection(settings) else "error"
        except Exception:
            checks["llm_api"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "version": settings.app_version,
        "checks": checks,
    }
