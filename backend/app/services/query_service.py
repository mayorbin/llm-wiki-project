# backend/app/services/query_service.py
"""
知识查询服务——LLM 查询、Wiki 页面 CRUD 和页面历史记录。

查询策略：
  1. 解析用户问题中的 [[wikilinks]]
  2. 加载相关 Wiki 页面内容
  3. 调用 LLM 综合回答
  4. 回答中保留 [[wikilinks]] 以供前端渲染

页面编辑使用维基引擎的原子写入，确保并发安全。
"""

import json
import uuid
import logging
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional, Literal

from app.config import get_settings
from app.storage.database import get_db
from app.storage.file_storage import safe_subdir, atomic_write, sha256
from app.engines.wiki_engine import (
    read_page, write_page, extract_wikilinks, all_wiki_pages,
    validate_wikilinks, read_index, write_index, update_index,
    remove_from_index, append_log, META_FILES,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


# ── 两阶段检索 Prompt 模板 ──

_STRUCTURE_KEYWORDS = [
    "有哪些文档", "多少篇", "列出", "目录", "概述", "总共", "几个", "统计", "索引", "汇总",
]

_UNKNOWN_HINT = "未找到与问题直接相关的文档，以下为知识库概览：\n\n"

_EXTRACTION_SYSTEM_PROMPT = """你是一个文本检索助手。从以下文档中提取与用户问题最相关的段落。
保留原始数据和数值。如果文档中确实没有相关信息，返回空。"""

_EXTRACTION_USER_PROMPT = """文档: {file_path}
内容:
{content}

问题: {question}

请提取与问题最相关的段落，按以下格式返回：
---
相关段落: <原文引用>
来源位置: <段落所在章节或行号范围>
---
（可返回多个段落块。如果文档不包含相关信息，返回"无相关内容"。
保留所有关键数据和表格信息。总计不超过 800 字。）"""

_SYNTHESIS_SYSTEM_PROMPT = """根据以下从多个文档中提取的相关段落，综合回答用户问题。
回答中使用 [[页面名]] 格式引用来源。每个关键事实附上来源标注。
中文回答。如果段落信息不足以回答问题，诚实说明。"""

_SYNTHESIS_USER_PROMPT = """相关段落:
{combined_excerpts}

可引用的 Wiki 页面（使用 [[页面名]] 格式引用）：
{page_refs}

问题: {question}

综合以上信息回答（使用 [[wikilinks]] 引用来源）："""


def _check_project_access(project_id: str, user_id: str):
    """校验用户对项目的访问权限。"""
    db = get_db("users")
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("项目不存在或无权访问")


def _project_wiki_dir(project_id: str) -> Path:
    """获取项目的 wiki/ 目录路径。"""
    settings = get_settings()
    wiki_dir = Path(settings.data_dir) / "projects" / project_id / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    return wiki_dir


def _page_history_path(project_id: str) -> Path:
    """获取页面编辑历史文件路径。"""
    settings = get_settings()
    return Path(settings.data_dir) / "projects" / project_id / "wiki" / ".page_history.json"


# ── LLM 查询 ──


def query_knowledge(
    project_id: str, user_id: str, question: str,
    model: Optional[str] = None,
) -> dict:
    """使用 LLM 查询知识库。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        question: 用户问题
        model: 使用的 LLM 模型（可选，默认使用全局配置）

    Returns:
        查询答案和相关页面引用
    """
    _check_project_access(project_id, user_id)

    wiki_dir = _project_wiki_dir(project_id)
    existing_pages = all_wiki_pages(wiki_dir)

    # 提取问题中的 wikilinks
    linked_pages = extract_wikilinks(question)

    # 收集相关页面内容作为上下文
    contexts = []
    sources_list = []

    # 加载索引和概览
    index_content = read_index(wiki_dir)
    if index_content:
        contexts.append(f"## Wiki Index\n{index_content[:3000]}")

    overview_path = wiki_dir / "overview.md"
    if overview_path.exists():
        overview = read_page(overview_path)
        if overview:
            contexts.append(f"## Overview\n{overview[:3000]}")
            sources_list.append("overview.md")

    # 加载明确链接的页面
    for link_name in linked_pages:
        found = False
        for section in ["sources", "entities", "concepts", "syntheses"]:
            page_path = wiki_dir / section / f"{link_name}.md"
            if page_path.exists():
                content = read_page(page_path)
                contexts.append(f"## {link_name}\n{content[:4000]}")
                sources_list.append(f"{section}/{link_name}.md")
                found = True
                break
        if not found:
            # 在 wiki/ 根目录查找
            page_path = wiki_dir / f"{link_name}.md"
            if page_path.exists():
                content = read_page(page_path)
                contexts.append(f"## {link_name}\n{content[:4000]}")
                sources_list.append(f"{link_name}.md")

    # 如果没有找到相关上下文，加载最近更新的几篇文章
    if len(contexts) <= 1:
        all_pages = sorted(
            [p for p in wiki_dir.rglob("*.md")
             if p.name not in ("index.md", "log.md", "overview.md", "lint-report.md", "health-report.md")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for p in all_pages[:5]:
            rel_path = str(p.relative_to(wiki_dir)).replace("\\", "/")
            if rel_path not in sources_list:
                content = read_page(p)
                contexts.append(f"## {p.stem}\n{content[:4000]}")
                sources_list.append(rel_path)

    # 调用 LLM
    combined_context = "\n\n---\n\n".join(contexts)

    system_prompt = """你是一个知识库查询助手。根据提供的 Wiki 页面内容回答用户问题。
- 在回答中使用 [[页面名]] 格式引用相关页面（wikilinks）
- 如果知识库中没有相关信息，诚实告知
- 提供简明的总结，突出关键信息
- 使用中文回答"""

    prompt = f"知识库内容：\n\n{combined_context}\n\n用户问题：{question}\n\n请根据知识库内容回答，使用 [[wikilinks]] 引用相关页面。"

    try:
        from app.engines.llm_engine import call_llm
        answer = call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            project_id=project_id,
        )
    except Exception as e:
        logger.error("LLM 查询失败", extra={"project_id": project_id, "error": str(e)})
        answer = f"查询失败：{str(e)}"

    # 提取回答中的 wikilinks 作为引用
    answer_links = extract_wikilinks(answer)

    return {
        "question": question,
        "answer": answer,
        "sources": sources_list,
        "references": answer_links,
        "searched_at": _now(),
    }


# ── 页面目录树 ──


def get_page_tree(project_id: str, user_id: str) -> dict:
    """获取 Wiki 页面的目录树结构。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
    """
    _check_project_access(project_id, user_id)

    wiki_dir = _project_wiki_dir(project_id)
    if not wiki_dir.exists():
        return {"sections": {}}

    sections = {}
    section_names = {
        "sources": "源文档",
        "entities": "实体",
        "concepts": "概念",
        "syntheses": "综合",
    }

    for section, label in section_names.items():
        section_dir = wiki_dir / section
        pages = []
        if section_dir.exists():
            for p in sorted(section_dir.rglob("*.md")):
                rel = str(p.relative_to(section_dir)).replace("\\", "/")
                stat = p.stat()
                pages.append({
                    "title": p.stem,
                    "path": f"{section}/{rel}",
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
        sections[section] = {"label": label, "pages": pages, "count": len(pages)}

    # 根目录的元页面
    meta_pages = []
    for meta in ["index.md", "overview.md", "log.md"]:
        meta_path = wiki_dir / meta
        if meta_path.exists():
            meta_pages.append({"title": meta.replace(".md", ""), "path": meta})

    return {"sections": sections, "meta_pages": meta_pages, "total_pages": sum(s["count"] for s in sections.values())}


# ── 页面 CRUD ──


def get_page(project_id: str, user_id: str, page_path: str) -> dict:
    """读取 Wiki 页面内容。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        page_path: 相对于 wiki/ 的页面路径
    """
    _check_project_access(project_id, user_id)

    wiki_dir = _project_wiki_dir(project_id)
    page_file = wiki_dir / page_path

    # 路径穿越防护
    try:
        safe_subdir(wiki_dir, page_path)
    except ValueError as e:
        raise ValueError(f"无效的页面路径: {e}")

    if not page_file.exists():
        raise ValueError(f"页面不存在: {page_path}")

    content = read_page(page_file)
    wikilinks = extract_wikilinks(content)
    broken_links = validate_wikilinks(content, wiki_dir)

    return {
        "path": page_path,
        "content": content,
        "title": page_file.stem,
        "wikilinks": wikilinks,
        "broken_links": [bl[0] for bl in broken_links],
        "size": len(content),
        "modified_at": datetime.fromtimestamp(
            page_file.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def update_page(project_id: str, user_id: str, page_path: str, content: str) -> dict:
    """编辑 Wiki 页面。

    自动校验 wikilinks，记录编辑历史。仅 owner/editor 可编辑。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        page_path: 相对于 wiki/ 的页面路径
        content: 新的页面内容
    """
    _check_project_access(project_id, user_id)

    db = get_db("users")
    role_row = db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not role_row or role_row["role"] not in ("owner", "editor"):
        raise PermissionError("仅有 owner 或 editor 可以编辑页面")

    wiki_dir = _project_wiki_dir(project_id)
    try:
        safe_subdir(wiki_dir, page_path)
    except ValueError as e:
        raise ValueError(f"无效的页面路径: {e}")

    page_file = wiki_dir / page_path

    # 保存旧内容用于历史记录
    old_content = read_page(page_file) if page_file.exists() else ""
    old_hash = sha256(old_content) if old_content else ""

    # 原子写入
    write_page(page_file, content)

    new_hash = sha256(content)

    # 记录编辑历史
    history = _load_page_history(project_id)
    if page_path not in history:
        history[page_path] = []
    history[page_path].append({
        "edited_by": user_id,
        "edited_at": _now(),
        "old_sha256": old_hash,
        "new_sha256": new_hash,
        "change_size": len(content) - len(old_content),
    })
    # 只保留最近 50 条历史
    if len(history[page_path]) > 50:
        history[page_path] = history[page_path][-50:]
    _save_page_history(project_id, history)

    # 更新日志
    append_log(wiki_dir, f"[{_now()[:10]}] EDITED `{page_path}` by {user_id}")

    logger.info("页面编辑成功", extra={"project_id": project_id, "page": page_path})

    wikilinks = extract_wikilinks(content)
    return {
        "path": page_path,
        "sha256": new_hash,
        "wikilinks": wikilinks,
        "size": len(content),
        "edited_at": _now(),
    }


def get_page_history(project_id: str, user_id: str, page_path: str) -> dict:
    """获取页面的编辑历史。

    Args:
        project_id: 项目 ID
        user_id: 当前用户 ID
        page_path: 相对于 wiki/ 的页面路径
    """
    _check_project_access(project_id, user_id)

    wiki_dir = _project_wiki_dir(project_id)
    try:
        safe_subdir(wiki_dir, page_path)
    except ValueError as e:
        raise ValueError(f"无效的页面路径: {e}")

    history = _load_page_history(project_id)
    page_history = history.get(page_path, [])

    return {
        "page": page_path,
        "edits": len(page_history),
        "history": page_history,
    }


def _load_page_history(project_id: str) -> dict:
    """加载页面编辑历史。"""
    hist_path = _page_history_path(project_id)
    if hist_path.exists():
        try:
            return json.loads(hist_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_page_history(project_id: str, history: dict):
    """保存页面编辑历史。"""
    hist_path = _page_history_path(project_id)
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
