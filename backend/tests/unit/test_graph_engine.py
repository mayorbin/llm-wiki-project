# backend/tests/unit/test_graph_engine.py
"""图谱引擎测试。"""

import json
import pytest
from pathlib import Path
from app.engines.graph_engine import (
    GraphEngine, _page_type, _node_id, _node_label, _sha256,
    TYPE_COLORS, EDGE_STYLES, COMMUNITY_COLORS,
)


@pytest.fixture
def engine(tmp_path):
    """创建使用临时目录的 GraphEngine。"""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    # 创建测试用 wiki 目录结构
    for sub in ("sources", "entities", "concepts", "syntheses"):
        (wiki_dir / sub).mkdir()
    graph_dir = tmp_path / "graph"
    return GraphEngine(wiki_dir, graph_dir)


class TestNodeHelpers:
    def test_source类型(self, engine):
        path = engine.wiki_dir / "sources" / "test.md"
        path.write_text("", encoding="utf-8")
        assert _page_type(path, engine.wiki_dir) == "source"

    def test_entity类型(self, engine):
        path = engine.wiki_dir / "entities" / "Person.md"
        path.write_text("", encoding="utf-8")
        assert _page_type(path, engine.wiki_dir) == "entity"

    def test_concept类型(self, engine):
        path = engine.wiki_dir / "concepts" / "Idea.md"
        path.write_text("", encoding="utf-8")
        assert _page_type(path, engine.wiki_dir) == "concept"

    def test_synthesis类型(self, engine):
        path = engine.wiki_dir / "syntheses" / "Answer.md"
        path.write_text("", encoding="utf-8")
        assert _page_type(path, engine.wiki_dir) == "synthesis"

    def test_unknown类型(self, engine):
        path = engine.wiki_dir / "misc.md"
        path.write_text("", encoding="utf-8")
        assert _page_type(path, engine.wiki_dir) == "unknown"

    def test_node_id生成(self, engine):
        path = engine.wiki_dir / "sources" / "my-paper.md"
        assert _node_id(path, engine.wiki_dir) == "sources/my-paper"

    def test_node_label(self, engine):
        path = engine.wiki_dir / "entities" / "Transformer.md"
        assert _node_label(path) == "Transformer"


class TestSHA256:
    def test_相同内容相同哈希(self):
        assert _sha256("hello") == _sha256("hello")

    def test_不同内容不同哈希(self):
        assert _sha256("hello") != _sha256("world")

    def test_空字符串可计算(self):
        result = _sha256("")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex is 64 chars


class TestExtractEdges:
    def test_空wiki无链接(self, engine):
        edges = engine.extract_edges(use_cache=False)
        assert edges == []

    def test_单页面无链接(self, engine):
        (engine.wiki_dir / "sources" / "lonely.md").write_text(
            "没有链接的页面", encoding="utf-8")
        edges = engine.extract_edges(use_cache=False)
        assert edges == []

    def test_两个页面互相链接(self, engine):
        (engine.wiki_dir / "sources" / "a.md").write_text(
            "参见 [[B]]", encoding="utf-8")
        (engine.wiki_dir / "entities" / "B.md").write_text(
            "来自 [[A]]", encoding="utf-8")
        edges = engine.extract_edges(use_cache=False)
        assert len(edges) == 2  # a → B, B → A

    def test_链接到不存在的页面被忽略(self, engine):
        (engine.wiki_dir / "sources" / "a.md").write_text(
            "参见 [[NonExistent]]", encoding="utf-8")
        edges = engine.extract_edges(use_cache=False)
        assert edges == []  # NonExistent 不存在，不生成边

    def test_边结构完整(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "---", encoding="utf-8")
        edges = engine.extract_edges(use_cache=False)
        assert len(edges) == 1
        edge = edges[0]
        assert edge["type"] == "EXTRACTED"
        assert edge["source"] == "sources/doc"
        assert edge["target"] == "Concept"
        assert "source_file" in edge


class TestCache:
    def test_首次构建创建缓存(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "---", encoding="utf-8")
        engine.extract_edges(use_cache=True)
        assert engine.cache_file.exists()
        cache = json.loads(engine.cache_file.read_text(encoding="utf-8"))
        assert "sha256" in cache
        assert "edges" in cache

    def test_缓存命中不重复读取(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "---", encoding="utf-8")
        # 第一次提取（写入缓存）
        edges1 = engine.extract_edges(use_cache=True)
        # 第二次提取（应从缓存读取）
        edges2 = engine.extract_edges(use_cache=True)
        assert len(edges1) == len(edges2)
        assert edges1 == edges2

    def test_内容变更后缓存失效(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "---", encoding="utf-8")
        (engine.wiki_dir / "entities" / "Person.md").write_text(
            "---", encoding="utf-8")
        # 第一次提取
        engine.extract_edges(use_cache=True)
        # 修改页面内容
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]] [[Person]]", encoding="utf-8")
        # 第二次提取应包含新边
        edges = engine.extract_edges(use_cache=True)
        assert len(edges) == 2  # doc → Concept, doc → Person

    def test_不使用缓存时每次都重新提取(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "---", encoding="utf-8")
        edges1 = engine.extract_edges(use_cache=False)
        # 修改后用 use_cache=False
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]] [[ExtraTarget]]", encoding="utf-8")
        (engine.wiki_dir / "entities" / "ExtraTarget.md").write_text(
            "---", encoding="utf-8")
        edges2 = engine.extract_edges(use_cache=False)
        assert len(edges1) == 1
        assert len(edges2) == 2


class TestCommunityDetection:
    def test_空图(self, engine):
        result = engine.detect_communities([], [])
        assert result == {}

    def test_单节点(self, engine):
        nodes = [{"id": "sources/only"}]
        edges = []
        result = engine.detect_communities(nodes, edges)
        assert "sources/only" in result
        assert "community" in result["sources/only"]
        assert "color" in result["sources/only"]

    def test_两个未连接节点分属不同社区(self, engine):
        nodes = [
            {"id": "sources/a"},
            {"id": "sources/b"},
        ]
        edges = []
        result = engine.detect_communities(nodes, edges)
        # 无连接时 Louvain 可能将其放入不同社区
        assert len(result) == 2

    def test_两个连接节点同属一个社区(self, engine):
        nodes = [
            {"id": "sources/a"},
            {"id": "sources/b"},
        ]
        edges = [{"source": "sources/a", "target": "sources/b"}]
        result = engine.detect_communities(nodes, edges)
        assert len(result) == 2
        # 相连节点应在同一社区
        assert result["sources/a"]["community"] == result["sources/b"]["community"]


class TestBuild:
    def test_空wiki构建返回空图(self, engine):
        result = engine.build(run_inference=False)
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["stats"]["node_count"] == 0

    def test_构建后生成graph_json(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "[[Concept]]", encoding="utf-8")
        (engine.wiki_dir / "concepts" / "Concept.md").write_text(
            "来自 [[doc]]", encoding="utf-8")
        result = engine.build(run_inference=False)
        assert result["stats"]["node_count"] == 2
        assert result["stats"]["edge_count"] == 2
        assert (engine.graph_dir / "graph.json").exists()

    def test_load加载已构建数据(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "test content", encoding="utf-8")
        engine.build(run_inference=False)
        loaded = engine.load()
        assert loaded is not None
        assert len(loaded["nodes"]) == 1

    def test_构建结果包含stats(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "test", encoding="utf-8")
        result = engine.build(run_inference=False)
        stats = result["stats"]
        assert "node_count" in stats
        assert "edge_count" in stats
        assert "extracted_edges" in stats
        assert "inferred_edges" in stats
        assert "community_count" in stats
        assert "build_time_seconds" in stats
        assert "built_at" in stats


class TestStats:
    def test_未构建时返回0(self, engine):
        stats = engine.stats()
        assert stats["node_count"] == 0

    def test_构建后返回正确统计(self, engine):
        (engine.wiki_dir / "sources" / "doc.md").write_text(
            "内容", encoding="utf-8")
        engine.build(run_inference=False)
        stats = engine.stats()
        assert stats["node_count"] == 1


class TestEdgeStyles:
    def test_EXTRACTED边样式(self):
        style = EDGE_STYLES["EXTRACTED"]
        assert "color" in style
        assert style["lineDash"] == []  # 实线

    def test_INFERRED边样式(self):
        style = EDGE_STYLES["INFERRED"]
        assert len(style["lineDash"]) == 2  # 虚线

    def test_AMBIGUOUS边样式(self):
        style = EDGE_STYLES["AMBIGUOUS"]
        assert "color" in style
        assert "lineWidth" in style

    def test_颜色映射完整性(self):
        for ptype in ("source", "entity", "concept", "synthesis", "unknown"):
            assert ptype in TYPE_COLORS

    def test_社区颜色数量(self):
        assert len(COMMUNITY_COLORS) == 20
