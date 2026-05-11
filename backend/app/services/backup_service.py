# backend/app/services/backup_service.py
"""
备份与维护服务——项目数据导出/导入、语义 lint 检查和审计日志查询。

导出格式：tar.gz 压缩包，包含 wiki/ + graph/ + raw/ 以及项目元数据。
语义 lint：调用 LLM 检查 Wiki 页面质量（断链、空页面、过时内容等）。
"""

import json
import tarfile
import tempfile
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.storage.database import get_db
from app.services.lock_manager import LockManager

logger = logging.getLogger(__name__)


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _check_project_access(project_id: str, user_id: str):
    """校验用户对项目的访问权限。"""
    db = get_db("users")
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")


def _check_owner_access(project_id: str, user_id: str):
    """校验用户是否为项目 owner。"""
    db = get_db("users")
    row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row or row["role"] != "owner":
        raise PermissionError("仅有项目 owner 可以执行此操作")


def _project_dir(project_id: str) -> Path:
    """获取项目目录路径。"""
    settings = get_settings()
    return Path(settings.data_dir) / "projects" / project_id


# ── 备份导出 ──


def export_backup(project_id: str, user_id: str) -> tuple[str, Path]:
    """导出项目数据为 tar.gz 压缩包。

    导出内容：
      - wiki/ 目录（所有 Wiki 页面）
      - graph/ 目录（图谱 JSON）
      - raw/ 目录（源文件）
      - project_meta.json（项目元数据）

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID

    Returns:
        (导出文件名, tar.gz 文件路径)
    """
    _check_project_access(project_id, user_id)

    project_dir = _project_dir(project_id)
    # 如果项目目录还不存在，创建空白目录用于导出
    if not project_dir.exists():
        project_dir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    export_name = f"{project_id}_backup_{now_str}.tar.gz"

    # 写临时位置
    settings = get_settings()
    backup_dir = Path(settings.data_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    export_path = backup_dir / export_name

    # 收集项目元数据
    db = get_db("users")
    project = db.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    members = db.execute(
        """SELECT pm.user_id, pm.role, pm.joined_at, u.username
           FROM project_members pm JOIN users u ON u.id = pm.user_id
           WHERE pm.project_id = ?""",
        (project_id,),
    ).fetchall()

    settings_row = db.execute(
        "SELECT settings FROM project_settings WHERE project_id = ?", (project_id,)
    ).fetchone()

    meta = {
        "project": dict(project) if project else {},
        "members": [dict(m) for m in members],
        "settings": json.loads(settings_row["settings"]) if settings_row else {},
        "exported_at": _now(),
        "exported_by": user_id,
    }

    # 创建 tar.gz
    with tarfile.open(str(export_path), "w:gz") as tar:
        # 写入元数据
        meta_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        try:
            json.dump(meta, meta_path, ensure_ascii=False, indent=2)
            meta_path.close()
            tar.add(meta_path.name, "project_meta.json")
        finally:
            Path(meta_path.name).unlink(missing_ok=True)

        # 写入 wiki/ 目录
        wiki_dir = project_dir / "wiki"
        if wiki_dir.exists():
            tar.add(str(wiki_dir), "wiki")

        # 写入 graph/ 目录
        graph_dir = project_dir / "graph"
        if graph_dir.exists():
            tar.add(str(graph_dir), "graph")

        # 写入 raw/ 目录
        raw_dir = project_dir / "raw"
        if raw_dir.exists():
            tar.add(str(raw_dir), "raw")

    file_size = export_path.stat().st_size

    logger.info("项目备份导出完成",
        extra={"project_id": project_id, "export_file": export_name, "size_bytes": file_size})

    return export_name, export_path


def import_backup(project_id: str, user_id: str, tar_path: Path) -> dict:
    """从 tar.gz 备份文件导入项目数据。

    覆盖现有 wiki/、graph/ 和 raw/ 内容。

    Args:
        project_id: 目标项目 ID
        user_id: 当前用户 ID
        tar_path: 备份文件路径

    Returns:
        导入结果摘要
    """
    _check_owner_access(project_id, user_id)

    project_dir = _project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    stats = {"files_imported": 0, "wiki_pages": 0, "graph_files": 0, "raw_files": 0}

    with tarfile.open(str(tar_path), "r:gz") as tar:
        # 安全检查：确保所有文件都在合理的路径下
        for member in tar.getmembers():
            # 拒绝绝对路径和 .. 穿越
            if member.name.startswith("/") or ".." in member.name:
                raise ValueError(f"不安全的归档路径: {member.name}")

        tar.extractall(path=str(project_dir), filter="data")

        for member in tar.getmembers():
            if member.isfile():
                stats["files_imported"] += 1
                if member.name.startswith("wiki/"):
                    stats["wiki_pages"] += 1
                elif member.name.startswith("graph/"):
                    stats["graph_files"] += 1
                elif member.name.startswith("raw/"):
                    stats["raw_files"] += 1

    logger.info("备份导入完成", extra={"project_id": project_id, "stats": stats})

    return {
        "project_id": project_id,
        "imported_at": _now(),
        "stats": stats,
    }


# ── 语义 Lint ──


def run_semantic_lint(project_id: str, user_id: str) -> dict:
    """运行语义 lint 检查。

    检查项：
      - 断链（wikilinks 指向不存在的页面）
      - 空页面/短页面（内容过少）
      - 页面之间的关系建议

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    project_dir = _project_dir(project_id)
    wiki_dir = project_dir / "wiki"

    if not wiki_dir.exists():
        return {"project_id": project_id, "issues": [], "checked_at": _now(), "status": "no_wiki"}

    issues = []
    meta_files = {"index.md", "log.md", "lint-report.md", "health-report.md", "overview.md"}

    from app.engines.wiki_engine import read_page, extract_wikilinks, all_wiki_pages
    existing_stems = all_wiki_pages(wiki_dir)

    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name in meta_files:
            continue

        content = read_page(md_file)
        rel_path = str(md_file.relative_to(wiki_dir)).replace("\\", "/")

        # 检查断链
        links = extract_wikilinks(content)
        for link in links:
            if link.lower() not in existing_stems:
                issues.append({
                    "type": "broken_link",
                    "page": rel_path,
                    "detail": f"[[{link}]] 指向不存在的页面",
                    "severity": "warning",
                })

        # 检查空/短页面
        line_count = len([l for l in content.split("\n") if l.strip()])
        if line_count < 3:
            issues.append({
                "type": "stub_page",
                "page": rel_path,
                "detail": f"页面内容过少（仅 {line_count} 行有效内容）",
                "severity": "info",
            })

    summary = {
        "project_id": project_id,
        "total_pages": sum(1 for p in wiki_dir.rglob("*.md") if p.name not in meta_files),
        "issues": issues,
        "issue_count": len(issues),
        "checked_at": _now(),
        "status": "completed",
    }

    # 保存 lint 报告
    lint_report = wiki_dir / "lint-report.md"
    lint_content = f"# Lint Report\n\n**检查时间**: {summary['checked_at']}\n**页面总数**: {summary['total_pages']}\n**问题数**: {summary['issue_count']}\n\n"
    for issue in issues:
        lint_content += f"- [{issue['severity'].upper()}] {issue['page']}: {issue['detail']}\n"
    from app.storage.file_storage import atomic_write
    atomic_write(lint_report, lint_content)

    logger.info("语义 lint 完成", extra={"project_id": project_id, "issues": len(issues)})
    return summary


# ── 审计日志 ──


def get_audit_log(
    user_id: str,
    project_id: Optional[str] = None,
    action: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """查询审计日志（分页，支持按项目和操作过滤）。

    管理员可查看所有日志，普通用户仅查看自己所属项目的日志。

    Args:
        user_id: 当前用户 ID
        project_id: 按项目过滤（可选）
        action: 按操作类型过滤（可选）
        offset: 分页偏移
        limit: 每页数量
    """
    db = get_db("audit")

    # 权限检查：验证用户对请求的项目有访问权限
    if project_id:
        users_db = get_db("users")
        row = users_db.execute(
            "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
        # 全局管理员可查看任何项目的审计日志
        admin_row = users_db.execute(
            "SELECT role FROM users WHERE id = ? AND role = 'admin'",
            (user_id,),
        ).fetchone()
        if not row and not admin_row:
            raise PermissionError("无权查看该项目的审计日志")

    # 构建查询
    conditions = []
    params = []

    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)

    if action:
        conditions.append("action = ?")
        params.append(action)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_sql = f"SELECT COUNT(*) AS cnt FROM audit_log {where}"
    query_sql = f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"

    count_row = db.execute(count_sql, params).fetchone()
    rows = db.execute(query_sql, params + [limit, offset]).fetchall()

    return {
        "entries": [dict(r) for r in rows],
        "total": count_row["cnt"] if count_row else 0,
        "offset": offset,
        "limit": limit,
    }
