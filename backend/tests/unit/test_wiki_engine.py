# backend/tests/unit/test_wiki_engine.py
"""Wiki 引擎测试。"""

import pytest
from pathlib import Path
from app.engines.wiki_engine import (
    extract_wikilinks, validate_wikilinks, update_index,
    remove_from_index, append_log, read_page, write_page,
)


class TestWikilinkExtraction:
    def test_基本链接(self):
        links = extract_wikilinks("参见 [[Transformer]] 和 [[Self-Attention]]")
        assert "Transformer" in links
        assert "Self-Attention" in links

    def test_别名链接只提取目标名(self):
        links = extract_wikilinks("[[Attention|注意力机制]] 是核心概念")
        assert "Attention" in links
        assert "注意力机制" not in links

    def test_无链接返回空(self):
        assert extract_wikilinks("普通文本，没有链接。") == []

    def test_多链接(self):
        links = extract_wikilinks("- [[A]]\n- [[B]]\n- [[C]]")
        assert len(links) == 3


class TestValidateWikilinks:
    def test_有效链接不报broken(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "Transformer.md").write_text("", encoding="utf-8")
        broken = validate_wikilinks("参见 [[Transformer]]", wiki_dir)
        assert broken == []

    def test_无效链接报broken(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        broken = validate_wikilinks("参见 [[NonExistent]]", wiki_dir)
        assert len(broken) == 1
        assert broken[0][0] == "NonExistent"


class TestIndexManagement:
    def test_更新index添加条目(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        update_index(wiki_dir, "- [测试文档](sources/test.md) — 摘要")
        content = (wiki_dir / "index.md").read_text(encoding="utf-8")
        assert "测试文档" in content
        assert "sources/test.md" in content

    def test_首次创建完整index(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        update_index(wiki_dir, "- [第一个](sources/first.md)")
        content = (wiki_dir / "index.md").read_text(encoding="utf-8")
        assert "Wiki Index" in content
        assert "Sources" in content

    def test_移除条目(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        update_index(wiki_dir, "- [待删除](sources/remove-me.md)")
        remove_from_index(wiki_dir, "remove-me", "Sources")
        content = (wiki_dir / "index.md").read_text(encoding="utf-8")
        assert "remove-me" not in content


class TestLogManagement:
    def test_追加日志新条目在前(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        append_log(wiki_dir, "## [2026-05-09] ingest | First")
        append_log(wiki_dir, "## [2026-05-09] ingest | Second")
        content = (wiki_dir / "log.md").read_text(encoding="utf-8")
        assert content.index("Second") < content.index("First")
