# backend/app/services/file_service.py
"""
文件服务——目录管理、文件上传/下载/移动/删除、变更检测和刷新摄入。

所有文件操作基于 safe_subdir() 进行路径穿越防护，
文件名使用 sanitize_filename() 净化。
"""

import os
import uuid
import json
import shutil
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, BinaryIO

from app.config import get_settings
from app.storage.database import get_db
from app.storage.file_storage import (
    safe_subdir, sanitize_filename, validate_extension,
    get_size_limit, file_sha256, atomic_write,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _project_raw_dir(project_id: str) -> Path:
    """获取项目的 raw/ 目录路径（均解析为绝对路径）。"""
    settings = get_settings()
    return (Path(settings.data_dir) / "projects" / project_id / "raw").resolve()


def _check_project_access(project_id: str, user_id: str):
    """校验用户对项目的访问权限，失败抛出 PermissionError。"""
    db = get_db("users")
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")


# ── 目录管理 ──


def list_directory_tree(project_id: str, user_id: str) -> dict:
    """返回项目的 raw/ 目录树结构。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    def _build_tree(path: Path) -> dict:
        """递归构建目录树。"""
        node = {
            "name": path.name,
            "path": str(path.relative_to(base_dir)).replace("\\", "/"),
            "type": "directory",
            "children": [],
        }
        # 收集子目录（排序）
        dirs = sorted(
            [p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")],
            key=lambda p: p.name.lower(),
        )
        for d in dirs:
            node["children"].append(_build_tree(d))

        # 收集文件（排序）
        files = sorted(
            [p for p in path.iterdir() if p.is_file() and not p.name.startswith(".")],
            key=lambda p: p.name.lower(),
        )
        for f in files:
            stat = f.stat()
            node["children"].append({
                "name": f.name,
                "path": str(f.relative_to(base_dir)).replace("\\", "/"),
                "type": "file",
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })

        return node

    tree = _build_tree(base_dir)
    # 根节点不需要自己的名称，直接返回 children
    return {"path": ".", "directories": tree["children"]}


def create_directory(project_id: str, user_id: str, dir_path: str):
    """在 raw/ 下创建子目录。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        dir_path: 相对 raw/ 的子目录路径
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, dir_path)
    target.mkdir(parents=True, exist_ok=True)

    logger.info("子目录创建成功", extra={"project_id": project_id, "dir": dir_path})


def delete_directory(project_id: str, user_id: str, dir_path: str):
    """删除 raw/ 下的空子目录。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        dir_path: 相对 raw/ 的子目录路径

    Raises:
        ValueError: 目录非空或路径不安全
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, dir_path)

    if str(target.resolve()) == str(base_dir.resolve()):
        raise ValueError("不能删除根目录")

    if not target.exists():
        raise ValueError(f"目录不存在: {dir_path}")

    # 仅允许删除空目录
    contents = list(target.iterdir())
    if contents:
        raise ValueError(f"目录非空，包含 {len(contents)} 个项目")

    target.rmdir()
    logger.info("空目录已删除", extra={"project_id": project_id, "dir": dir_path})


# ── 文件上传 ──


def upload_file(
    project_id: str, user_id: str, file: BinaryIO, filename: str,
    subdir: str = "",
) -> dict:
    """上传单个文件到 raw/ 目录。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        file: 上传的文件流
        filename: 原始文件名
        subdir: 子目录路径（为空则存到 raw/ 根目录）

    Returns:
        上传结果元数据
    """
    _check_project_access(project_id, user_id)

    clean_name = sanitize_filename(filename)

    # 扩展名白名单校验
    if not validate_extension(clean_name):
        raise ValueError(f"不支持的文件类型: {Path(clean_name).suffix}")

    # 大小限制校验
    settings = get_settings()
    max_size = min(
        get_size_limit(clean_name),
        settings.max_upload_size_mb * 1024 * 1024,
    )

    base_dir = _project_raw_dir(project_id)
    dest_dir = safe_subdir(base_dir, subdir) if subdir else base_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / clean_name

    # 避免覆盖：重名时追加数字后缀
    counter = 1
    stem = Path(clean_name).stem
    suffix = Path(clean_name).suffix
    while dest_path.exists():
        new_name = f"{stem}_{counter}{suffix}"
        dest_path = dest_dir / new_name
        counter += 1

    # 写入文件（分块复制以支持大文件）
    total_size = 0
    with open(dest_path, "wb") as f:
        while True:
            chunk = file.read(8192)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size:
                dest_path.unlink()
                raise ValueError(f"文件大小超过限制 ({max_size // 1024 // 1024} MB)")
            f.write(chunk)

    # 计算 SHA256
    sha = file_sha256(dest_path)
    mtime = datetime.fromtimestamp(
        dest_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    relative_path = str(dest_path.relative_to(base_dir)).replace("\\", "/")

    logger.info("文件上传成功",
        extra={"project_id": project_id, "file": relative_path, "size": total_size})

    return {
        "path": relative_path,
        "name": dest_path.name,
        "original_name": filename,
        "size_bytes": total_size,
        "sha256": sha,
        "modified_at": mtime,
        "uploaded_by": user_id,
    }


def upload_batch(
    project_id: str, user_id: str, files: list[tuple[BinaryIO, str]],
    subdir: str = "",
) -> dict:
    """批量上传文件。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        files: [(file_stream, filename), ...] 列表
        subdir: 子目录路径

    Returns:
        汇总结果
    """
    _check_project_access(project_id, user_id)

    results = []
    errors = []
    for f_stream, f_name in files:
        try:
            result = upload_file(project_id, user_id, f_stream, f_name, subdir)
            results.append(result)
        except Exception as e:
            errors.append({"filename": f_name, "error": str(e)})

    return {
        "uploaded": len(results),
        "failed": len(errors),
        "files": results,
        "errors": errors,
    }


# ── 文件查询 ──


def list_files(
    project_id: str, user_id: str,
    subdir: str = "", offset: int = 0, limit: int = 50,
) -> dict:
    """列出 raw/ 目录下的文件列表（分页）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        subdir: 子目录路径
        offset: 分页偏移
        limit: 每页数量
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target_dir = safe_subdir(base_dir, subdir) if subdir else base_dir
    if not target_dir.exists():
        return {"files": [], "total": 0, "offset": offset, "limit": limit}

    all_files = sorted(
        [p for p in target_dir.iterdir() if p.is_file() and not p.name.startswith(".")],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    total = len(all_files)
    page = all_files[offset:offset + limit]

    files = []
    for f in page:
        stat = f.stat()
        files.append({
            "name": f.name,
            "path": str(f.relative_to(base_dir)).replace("\\", "/"),
            "type": "file",
            "size_bytes": stat.st_size,
            "sha256": file_sha256(f),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return {"files": files, "total": total, "offset": offset, "limit": limit}


def get_file_detail(project_id: str, user_id: str, file_path: str) -> dict:
    """获取文件详情（含 SHA256 和修改时间）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        file_path: 相对于 raw/ 的文件路径
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, file_path)

    if not target.exists() or not target.is_file():
        raise ValueError(f"文件不存在: {file_path}")

    stat = target.stat()
    return {
        "name": target.name,
        "path": str(target.relative_to(base_dir)).replace("\\", "/"),
        "size_bytes": stat.st_size,
        "sha256": file_sha256(target),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "extension": target.suffix.lower(),
    }


def download_file(project_id: str, user_id: str, file_path: str) -> tuple[str, Path]:
    """获取文件路径用于下载。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        file_path: 相对于 raw/ 的文件路径

    Returns:
        (content_type_guess, file_path)
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, file_path)

    if not target.exists() or not target.is_file():
        raise ValueError(f"文件不存在: {file_path}")

    # MIME 类型猜测
    ext = target.suffix.lower()
    mime_map = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".xml": "application/xml",
        ".html": "text/html",
        ".htm": "text/html",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ipynb": "application/json",
    }
    content_type = mime_map.get(ext, "application/octet-stream")
    return content_type, target


# ── 文件操作 ──


def delete_file(project_id: str, user_id: str, file_path: str):
    """删除文件（级联删除关联的摄入记录和 wiki 页面）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        file_path: 相对于 raw/ 的文件路径
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, file_path)

    if not target.exists() or not target.is_file():
        raise ValueError(f"文件不存在: {file_path}")

    target.unlink()

    # 级联：标记关联摄入任务
    relative_path = str(target.relative_to(base_dir)).replace("\\", "/")
    tasks_db = get_db("tasks")
    tasks_db.execute(
        "UPDATE task_queue SET error_detail = COALESCE(error_detail, '') || ' [源文件已删除]' "
        "WHERE project_id = ? AND file_paths LIKE ?",
        (project_id, f"%{relative_path}%"),
    )
    tasks_db.commit()

    logger.info("文件已删除（级联）", extra={"project_id": project_id, "file": relative_path})


def move_file(project_id: str, user_id: str, source_path: str, dest_dir: str) -> dict:
    """移动文件到指定子目录。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        source_path: 源文件路径（相对 raw/）
        dest_dir: 目标子目录（相对 raw/）
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    source = safe_subdir(base_dir, source_path)
    dest_directory = safe_subdir(base_dir, dest_dir)

    if not source.exists() or not source.is_file():
        raise ValueError(f"源文件不存在: {source_path}")

    dest_directory.mkdir(parents=True, exist_ok=True)
    dest = dest_directory / source.name

    # 目标文件已存在则加后缀
    counter = 1
    stem = source.stem
    suffix = source.suffix
    while dest.exists():
        dest = dest_directory / f"{stem}_{counter}{suffix}"
        counter += 1

    shutil.move(str(source), str(dest))

    new_path = str(dest.relative_to(base_dir)).replace("\\", "/")
    logger.info("文件移动成功",
        extra={"project_id": project_id, "from": source_path, "to": new_path})

    return {
        "source": source_path,
        "destination": new_path,
        "name": dest.name,
    }


# ── 变更检测 ──


def detect_changes(project_id: str, user_id: str) -> dict:
    """检测 raw/ 目录下所有文件的变更（基于 SHA256 + mtime）。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID

    Returns:
        变更检测结果
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    if not base_dir.exists():
        return {"changed": [], "added": [], "deleted": [], "total_files": 0}

    # 加载上次快照
    snapshot_file = base_dir / ".file_snapshot.json"
    previous = {}
    if snapshot_file.exists():
        try:
            previous = json.loads(snapshot_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 扫描当前文件
    current: dict[str, dict] = {}
    for f in base_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            rel = str(f.relative_to(base_dir)).replace("\\", "/")
            current[rel] = {
                "sha256": file_sha256(f),
                "mtime": f.stat().st_mtime,
                "size": f.stat().st_size,
            }

    # 比较差异
    changed = []
    added = []
    deleted = []

    for path, info in current.items():
        if path in previous:
            prev = previous[path]
            if info["sha256"] != prev.get("sha256") or info["mtime"] != prev.get("mtime"):
                changed.append({"path": path, "reason": "内容或时间变化"})
        else:
            added.append(path)

    for path in previous:
        if path not in current:
            deleted.append(path)

    # 保存新快照
    snapshot_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "changed": changed,
        "added": added,
        "deleted": deleted,
        "total_files": len(current),
        "checked_at": _now(),
    }


def refresh_files(project_id: str, user_id: str, file_paths: list[str]) -> dict:
    """重新摄入指定的文件列表。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        file_paths: 要重新摄入的文件路径列表
    """
    _check_project_access(project_id, user_id)

    base_dir = _project_raw_dir(project_id)
    results = []
    errors = []

    for fp in file_paths:
        try:
            target = safe_subdir(base_dir, fp)
            if not target.exists() or not target.is_file():
                errors.append({"path": fp, "error": "文件不存在"})
                continue
            # 创建摄入任务
            task_id = _create_ingest_task(project_id, user_id, [fp])
            results.append({"path": fp, "task_id": task_id, "status": "queued"})
        except Exception as e:
            errors.append({"path": fp, "error": str(e)})

    return {"results": results, "errors": errors, "total": len(file_paths)}


def refresh_all_changed(project_id: str, user_id: str) -> dict:
    """重新摄入所有检测到变更的文件。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    changes = detect_changes(project_id, user_id)
    all_changed = [
        item["path"] if isinstance(item, dict) else item
        for item in changes["changed"] + changes["added"]
    ]

    if not all_changed:
        return {"message": "没有检测到变更", "tasks": []}

    return refresh_files(project_id, user_id, all_changed)


def delete_file(project_id: str, user_id: str, file_path: str):
    """删除 raw/ 下的指定文件。

    Args:
        project_id: 项目 ID
        user_id: 操作者用户 ID
        file_path: 文件路径（相对 raw/，如 "customers.xlsx" 或 "子目录/file.pdf"）
    """
    # 权限：仅 owner 和 editor 可删除
    db = get_db("users")
    role = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not role or role["role"] not in ("owner", "editor"):
        raise PermissionError("仅有 owner 或 editor 可以删除文件")

    base_dir = _project_raw_dir(project_id)
    target = safe_subdir(base_dir, file_path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"文件不存在: {file_path}")

    # 删除文件
    target.unlink()
    logger.info("文件已删除", extra={"project_id": project_id, "file": file_path, "user": user_id})

    # 尝试清理空目录
    parent = target.parent
    if parent != base_dir and not any(parent.iterdir()):
        try:
            parent.rmdir()
        except OSError:
            pass


def _create_ingest_task(project_id: str, user_id: str, file_paths: list[str]) -> str:
    """创建摄入任务并返回 task_id。"""
    from app.engines.llm_engine import call_llm

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = _now()

    db = get_db("tasks")
    db.execute(
        """INSERT INTO task_queue (task_id, project_id, action, file_paths, status, progress,
           created_by, created_at)
           VALUES (?, ?, 'ingest', ?, 'queued', 0, ?, ?)""",
        (task_id, project_id, json.dumps(file_paths, ensure_ascii=False), user_id, now),
    )
    db.commit()

    return task_id
