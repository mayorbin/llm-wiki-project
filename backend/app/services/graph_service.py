# backend/app/services/graph_service.py
"""
图谱服务——封装 GraphEngine 的构建、查询和统计功能。

构建流程（两阶段）：
  Pass 1（确定性）：解析 [[wikilinks]] → EXTRACTED 边
  Pass 2（语义推断，可选）：LLM 推断隐式关系 → INFERRED 边
  Pass 3（社区检测）：Louvain 算法聚类

图谱输出为 vis.js / G6 兼容的 JSON 格式。
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from app.config import get_settings
from app.storage.database import get_db
from app.engines.graph_engine import GraphEngine
from app.services.lock_manager import LockManager

logger = logging.getLogger(__name__)


def _check_project_access(project_id: str, user_id: str):
    """校验用户对项目的访问权限。"""
    db = get_db("users")
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")


def _get_project_dirs(project_id: str) -> tuple[Path, Path]:
    """获取项目的 wiki/ 和 graph/ 目录路径。"""
    settings = get_settings()
    project_dir = Path(settings.data_dir) / "projects" / project_id
    wiki_dir = project_dir / "wiki"
    graph_dir = project_dir / "graph"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)
    return wiki_dir, graph_dir


def _get_lock_manager() -> LockManager:
    """获取锁管理器实例。"""
    settings = get_settings()
    return LockManager(Path(settings.data_dir))


def get_graph_data(project_id: str, user_id: str) -> dict:
    """获取已构建的图谱 JSON 数据。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    wiki_dir, graph_dir = _get_project_dirs(project_id)
    engine = GraphEngine(wiki_dir=wiki_dir, graph_dir=graph_dir)
    data = engine.load()

    if not data:
        return {
            "nodes": [],
            "edges": [],
            "stats": {"node_count": 0, "edge_count": 0, "built": False},
        }

    return data


def build_graph(project_id: str, user_id: str, run_inference: bool = False) -> dict:
    """触发图谱构建。

    需要获取项目写锁（构建过程会写入 wiki/ 和 graph/ 目录）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        run_inference: 是否执行 LLM 语义推断（Pass 2，消耗 token）
    """
    _check_project_access(project_id, user_id)

    db = get_db("users")
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not role_row or role_row["role"] not in ("owner", "editor"):
        raise PermissionError("仅有 owner 或 editor 可以构建图谱")

    lock_mgr = _get_lock_manager()
    lock = lock_mgr.acquire_project_write(project_id, timeout=300)

    try:
        wiki_dir, graph_dir = _get_project_dirs(project_id)
        engine = GraphEngine(wiki_dir=wiki_dir, graph_dir=graph_dir)
        data = engine.build(run_inference=run_inference)

        logger.info("图谱构建完成", extra={
            "project_id": project_id,
            "nodes": data["stats"]["node_count"],
            "edges": data["stats"]["edge_count"],
        })

        return data
    finally:
        lock_mgr.release(lock)


def get_graph_stats(project_id: str, user_id: str) -> dict:
    """获取图谱统计信息（不触发构建，仅读取缓存）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    wiki_dir, graph_dir = _get_project_dirs(project_id)
    engine = GraphEngine(wiki_dir=wiki_dir, graph_dir=graph_dir)

    data = engine.load()
    if data:
        stats = data["stats"]
    else:
        # 统计页面数量（不构建图谱）
        page_count = sum(
            1 for p in wiki_dir.rglob("*.md")
            if p.name not in ("index.md", "log.md", "overview.md",
                              "lint-report.md", "health-report.md")
        ) if wiki_dir.exists() else 0
        stats = {
            "node_count": page_count,
            "edge_count": 0,
            "extracted_edges": 0,
            "inferred_edges": 0,
            "community_count": 0,
            "built": False,
        }

    # 附加项目统计
    stats["project_id"] = project_id
    stats["wiki_directory_exists"] = wiki_dir.exists()
    stats["graph_json_exists"] = (graph_dir / "graph.json").exists()

    return stats
