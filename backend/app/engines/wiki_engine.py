# backend/app/engines/wiki_engine.py
"""
Wiki 页面引擎——管理 markdown 页面的 CRUD、wikilink 和索引。

Wiki 页面格式（YAML frontmatter + Markdown body）：
  ---
  title: "页面标题"
  type: source | entity | concept | synthesis
  tags: []
  sources: []
  last_updated: 2026-05-09
  ---

  ## Summary
  页面内容...

Wikilink 语法：[[PageName]] 或 [[PageName|显示文本]]
"""

import re
import logging
from pathlib import Path
from typing import Optional

from app.storage.file_storage import atomic_write, sha256

logger = logging.getLogger(__name__)

# Wikilink 正则：[[PageName]] 或 [[PageName|显示文本]]
WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")

# 排除在 all_wiki_pages 之外的元文件
META_FILES = {"index.md", "log.md", "lint-report.md", "health-report.md", "overview.md"}


def read_page(path: Path) -> str:
    """读取 Wiki 页面内容，文件不存在返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_page(path: Path, content: str):
    """原子写入 Wiki 页面。"""
    atomic_write(path, content)


def extract_wikilinks(content: str) -> list[str]:
    """从页面内容提取所有 [[WikiLink]] 的目标名称（不含别名部分）。"""
    return [m[0].strip() for m in WIKILINK_RE.findall(content)]


def all_wiki_pages(wiki_dir: Path) -> set[str]:
    """返回 wiki/ 目录下所有页面的 stem（小写），用于 wikilink 验校。"""
    if not wiki_dir.exists():
        return set()
    pages: set[str] = set()
    for p in wiki_dir.rglob("*.md"):
        if p.name not in META_FILES:
            pages.add(p.stem.lower())
    return pages


def validate_wikilinks(content: str, wiki_dir: Path) -> list[tuple[str, str]]:
    """校验页面中所有 wikilink 的有效性。

    Returns:
        broken_links 列表，每项为 (链接文本, 目标页面名)。
    """
    existing = all_wiki_pages(wiki_dir)
    broken: list[tuple[str, str]] = []
    for link_text in extract_wikilinks(content):
        if link_text.lower() not in existing:
            broken.append((link_text, link_text))
    return broken


def write_index(wiki_dir: Path, content: str):
    """写入 index.md 的完整内容。"""
    write_page(wiki_dir / "index.md", content)


def read_index(wiki_dir: Path) -> str:
    """读取 index.md 内容。"""
    return read_page(wiki_dir / "index.md")


def update_index(wiki_dir: Path, entry: str, section: str = "Sources"):
    """在 index.md 指定 section 下追加一条条目。

    如果 index.md 不存在则创建默认结构。
    """
    index_path = wiki_dir / "index.md"
    content = read_page(index_path)

    if not content:
        content = (
            "# Wiki Index\n\n"
            "## Overview\n- [Overview](overview.md) — 全局综合\n\n"
            "## Sources\n\n## Entities\n\n## Concepts\n\n## Syntheses\n"
        )

    section_header = f"## {section}"
    if section_header in content:
        content = content.replace(
            section_header + "\n", section_header + "\n" + entry + "\n"
        )
    else:
        content += f"\n{section_header}\n{entry}\n"

    write_page(index_path, content)


def remove_from_index(wiki_dir: Path, stem: str, section: str = "Sources"):
    """从 index.md 中移除包含指定 stem 的条目行。"""
    index_path = wiki_dir / "index.md"
    content = read_page(index_path)
    lines = content.split("\n")
    pattern = f"({section.lower()}/{stem}.md)"
    filtered = [line for line in lines if pattern not in line.lower()]
    write_page(index_path, "\n".join(filtered))


def append_log(wiki_dir: Path, entry: str):
    """向 wiki/log.md 追加日志条目（新条目在最前面）。"""
    log_path = wiki_dir / "log.md"
    existing = read_page(log_path)
    new_content = entry.strip() + "\n\n" + existing
    write_page(log_path, new_content)


def cleanup_stale_tmp(wiki_dir: Path):
    """清理残留的 .tmp 文件（写入过程中崩溃遗留）。"""
    count = 0
    for tmp in wiki_dir.rglob("*.tmp"):
        try:
            tmp.unlink()
            count += 1
        except OSError:
            pass
    if count > 0:
        logger.info(f"清理残留临时文件: {count} 个")
