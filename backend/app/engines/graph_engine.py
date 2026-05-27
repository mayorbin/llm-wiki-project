# backend/app/engines/graph_engine.py
"""
知识图谱引擎——NetworkX 图构建 + Louvain 社区检测 + G6 JSON 输出。

两阶段构建：
  Pass 1（确定性）：解析所有 [[wikilinks]] → EXTRACTED 边
  Pass 2（语义推断）：LLM 推断隐式关系 → INFERRED / AMBIGUOUS 边
  Pass 3（社区检测）：Louvain 算法聚类 + 色值映射

SHA256 缓存：仅重建内容变化的页面，未变化的复用缓存。
"""

import json
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import networkx as nx
from networkx.algorithms import community as nx_community

from app.engines.wiki_engine import read_page, extract_wikilinks, all_wiki_pages, META_FILES

logger = logging.getLogger(__name__)

# 节点类型 → G6 颜色
TYPE_COLORS = {
    "source": "#4CAF50",
    "entity": "#2196F3",
    "concept": "#FF9800",
    "synthesis": "#9C27B0",
    "unknown": "#9E9E9E",
}

# 边类型 → G6 样式
EDGE_STYLES = {
    "EXTRACTED": {"color": "#555555", "lineWidth": 1, "lineDash": []},
    "INFERRED": {"color": "#FF5722", "lineWidth": 1.5, "lineDash": [5, 5]},
    "AMBIGUOUS": {"color": "#BDBDBD", "lineWidth": 0.5, "lineDash": [2, 4]},
}

# Louvain 社区调色板（G6 20 色方案）
COMMUNITY_COLORS = [
    "#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16", "#E8684A",
    "#6DC8EC", "#9270CA", "#FF9D4D", "#269A99", "#FF99C3",
    "#5B8FF9", "#BDD2FD", "#5AD8A6", "#BDEFDB", "#5D7092",
    "#C2C8D5", "#F6BD16", "#FBE5A2", "#E8684A", "#F6C3B7",
]


def _page_type(page_path: Path, wiki_dir: Path) -> str:
    """根据文件路径推断页面类型。"""
    rel = str(page_path.relative_to(wiki_dir))
    if rel.startswith("sources"):
        return "source"
    elif rel.startswith("entities"):
        return "entity"
    elif rel.startswith("concepts"):
        return "concept"
    elif rel.startswith("syntheses"):
        return "synthesis"
    return "unknown"


def _node_id(page_path: Path, wiki_dir: Path) -> str:
    """从文件路径生成图节点 ID。"""
    rel = page_path.relative_to(wiki_dir)
    return str(rel.with_suffix("")).replace("\\", "/")


def _node_label(page_path: Path) -> str:
    """从文件名生成节点标签。"""
    return page_path.stem


def _sha256(text: str) -> str:
    """计算字符串 SHA256。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GraphEngine:
    """知识图谱构建引擎。"""

    def __init__(self, wiki_dir: Path, graph_dir: Path):
        self.wiki_dir = Path(wiki_dir)
        self.graph_dir = Path(graph_dir)
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.graph_dir / ".cache.json"

    # ── 缓存 ──

    def _load_cache(self) -> dict:
        """加载 SHA256 缓存。"""
        if self.cache_file.exists():
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        return {}

    def _save_cache(self, cache: dict):
        """保存 SHA256 缓存。"""
        self.cache_file.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _compute_page_hashes(self, pages: list[Path]) -> dict[str, str]:
        """计算所有页面的 SHA256 哈希。

        Returns:
            {relative_path: sha256_hex} 映射。
        """
        hashes = {}
        for page_path in pages:
            rel = str(page_path.relative_to(self.wiki_dir)).replace("\\", "/")
            content = read_page(page_path)
            hashes[rel] = _sha256(content)
        return hashes

    # ── Pass 1: 确定性链接提取 ──

    def extract_edges(self, use_cache: bool = True) -> list[dict]:
        """从所有 wiki 页面的 [[wikilinks]] 中提取显式边。

        Args:
            use_cache: 若为 True，对内容未变化的页面复用缓存中的边。

        Returns:
            边列表，每条边包含 source, target, type, source_file。
        """
        cache = self._load_cache() if use_cache else {}
        sha256_cache = cache.get("sha256", {})
        edges_cache = cache.get("edges", {})

        pages = [p for p in sorted(self.wiki_dir.rglob("*.md"))
                 if p.name not in META_FILES]
        existing_stems = all_wiki_pages(self.wiki_dir)

        all_edges: list[dict] = []
        new_sha256: dict[str, str] = {}
        new_edges_cache: dict[str, list[dict]] = {}

        for page_path in pages:
            rel_path = str(page_path.relative_to(self.wiki_dir)).replace("\\", "/")
            content = read_page(page_path)
            current_hash = _sha256(content)
            new_sha256[rel_path] = current_hash
            source_id = _node_id(page_path, self.wiki_dir)

            # 缓存命中：内容未变化且有缓存边
            if (use_cache
                    and sha256_cache.get(rel_path) == current_hash
                    and source_id in edges_cache):
                cached = edges_cache[source_id]
                all_edges.extend(cached)
                new_edges_cache[source_id] = cached
                continue

            # 缓存未命中：重新提取 wikilinks
            source_edges = []
            for target_name in extract_wikilinks(content):
                if target_name.lower() in existing_stems:
                    source_edges.append({
                        "source": source_id,
                        "target": target_name,
                        "type": "EXTRACTED",
                        "source_file": rel_path,
                    })

            all_edges.extend(source_edges)
            new_edges_cache[source_id] = source_edges

        # 保存更新后的缓存
        if use_cache:
            cache["sha256"] = new_sha256
            cache["edges"] = new_edges_cache
            self._save_cache(cache)

        return all_edges

    # ── Pass 2: 语义关系推断 ──

    def infer_edges(self, pages_context: str) -> list[dict]:
        """使用 LLM 推断页面间的隐式关系。

        Args:
            pages_context: 页面摘要文本（由调用方组装）

        Returns:
            INFERRED 或 AMBIGUOUS 边列表。
        """
        from app.engines.llm_engine import call_llm

        prompt = f"""分析以下 Wiki 页面之间的关系，找出隐式关联（未通过 [[wikilinks]] 显式链接的关系）。

页面内容：
{pages_context}

返回仅一个 JSON 数组，每项格式：
{{"source": "页面路径", "target": "页面路径", "confidence": 0.0-1.0, "reason": "关系简述"}}

仅返回 confidence >= 0.7 的关系。不返回已有显式链接的关系。"""

        try:
            raw = call_llm(prompt=prompt, max_tokens=4096)
            # 清理可能的 markdown 代码块
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw[raw.index("\n"):].strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
            inferred = json.loads(raw)
            return [
                {
                    "source": item["source"],
                    "target": item["target"],
                    "type": "INFERRED" if item["confidence"] >= 0.7 else "AMBIGUOUS",
                    "confidence": item["confidence"],
                    "reason": item.get("reason", ""),
                }
                for item in inferred
                if isinstance(item, dict) and "source" in item and "target" in item
            ]
        except Exception as e:
            logger.warning(f"语义关系推断失败: {e}")
            return []

    # ── Pass 3: 社区检测 ──

    def detect_communities(self, nodes: list[dict], edges: list[dict]) -> dict:
        """Louvain 社区检测，返回每个节点的社区 ID 和颜色。

        Args:
            nodes: 节点列表，每项至少含 "id"。
            edges: 边列表，每项含 "source" 和 "target"。

        Returns:
            {node_id: {"community": int, "color": str}} 映射。
        """
        G = nx.Graph()
        for node in nodes:
            G.add_node(node["id"])
        for edge in edges:
            G.add_edge(edge["source"], edge["target"])

        try:
            communities = nx_community.louvain_communities(G, seed=42)
        except Exception:
            # 图太小或没有边，每个节点一个社区
            return {
                node["id"]: {
                    "community": i,
                    "color": COMMUNITY_COLORS[i % len(COMMUNITY_COLORS)],
                }
                for i, node in enumerate(nodes)
            }

        result = {}
        for comm_id, members in enumerate(communities):
            color = COMMUNITY_COLORS[comm_id % len(COMMUNITY_COLORS)]
            for member in members:
                result[member] = {"community": comm_id, "color": color}

        # 确保所有节点都在结果中（孤立节点可能不在任何社区）
        for i, node in enumerate(nodes):
            if node["id"] not in result:
                result[node["id"]] = {
                    "community": -1,
                    "color": COMMUNITY_COLORS[i % len(COMMUNITY_COLORS)],
                }

        return result

    # ── 构建主流程 ──

    def build(self, run_inference: bool = True) -> dict:
        """执行完整的图谱构建流程。

        Args:
            run_inference: 是否运行 Pass 2（LLM 语义推断）。

        Returns:
            G6 兼容的 JSON 数据（nodes + edges + communities + stats）。
        """
        t0 = datetime.now(timezone.utc)
        logger.info("图谱构建开始")

        # 清理孤立 wiki 页面（对应 raw 文件已删除的 source 页面）
        raw_dir = self.wiki_dir.parent / "raw"
        sources_dir = self.wiki_dir / "sources"
        if sources_dir.exists() and raw_dir.exists():
            for page in list(sources_dir.glob("*.md")):
                # 尝试根据 wiki 页面的 source_file 元数据或 slug 反查 raw 文件
                # 优先从 frontmatter 中读取 source_file
                content = read_page(page)
                match = re.search(r'(?m)^source_file:\s*(.+)$', content)
                raw_path = match.group(1).strip() if match else None
                if raw_path and not (raw_dir / raw_path).exists():
                    page.unlink()
                    try:
                        from app.engines.wiki_engine import remove_from_index
                        remove_from_index(self.wiki_dir, page.stem, "sources")
                    except Exception:
                        pass
                    logger.info("已清理孤立 wiki 页面", extra={"page": str(page), "raw": raw_path})

        # 收集所有 wiki 页面
        pages = [p for p in self.wiki_dir.rglob("*.md")
                 if p.name not in META_FILES]

        # 构建节点列表
        nodes = []
        for page_path in pages:
            node_id = _node_id(page_path, self.wiki_dir)
            ptype = _page_type(page_path, self.wiki_dir)
            label = _node_label(page_path)
            nodes.append({
                "id": node_id,
                "label": label,
                "type": ptype,
                "color": TYPE_COLORS.get(ptype, TYPE_COLORS["unknown"]),
                "path": str(page_path.relative_to(self.wiki_dir)).replace("\\", "/"),
            })

        # 按 id 排序以保证稳定输出
        nodes.sort(key=lambda n: n["id"])

        # Pass 1: 提取显式边
        extracted_edges = self.extract_edges(use_cache=True)

        # Pass 2: 推断隐式边（可选，消耗 LLM token）
        inferred_edges = []
        if run_inference:
            # 组装页面上下文（取前 20 页避免 token 过长）
            context_parts = []
            for page_path in pages[:20]:
                node_id = _node_id(page_path, self.wiki_dir)
                content = read_page(page_path)[:2000]  # 每页截取前 2000 字符
                context_parts.append(f"### {node_id}\n{content}")
            pages_context = "\n\n---\n\n".join(context_parts)
            inferred_edges = self.infer_edges(pages_context)

        all_edges = extracted_edges + inferred_edges

        # 清理孤立 entity / concept 页面（没有任何边连接的 → 孤儿节点）
        # 构建 stem → node_id 映射，用于将 edge 的 wikilink 名称解析为节点 ID
        stem_to_ids: dict[str, list[str]] = {}
        for p in pages:
            stem_to_ids.setdefault(p.stem.lower(), []).append(_node_id(p, self.wiki_dir))
        connected_ids: set[str] = set()
        for e in all_edges:
            connected_ids.add(e["source"])
            for nid in stem_to_ids.get(e["target"].lower(), []):
                connected_ids.add(nid)
        for section in ("entities", "concepts"):
            section_dir = self.wiki_dir / section
            if section_dir.exists():
                for page in list(section_dir.glob("*.md")):
                    node_id = _node_id(page, self.wiki_dir)
                    if node_id not in connected_ids:
                        page.unlink()
                        try:
                            from app.engines.wiki_engine import remove_from_index
                            remove_from_index(self.wiki_dir, page.stem, section)
                        except Exception:
                            pass
                        logger.info("已清理孤立%s页面", section, extra={"page": str(page)})

        # 清理后重建节点列表（可能有页面被删除了）
        pages = [p for p in self.wiki_dir.rglob("*.md")
                 if p.name not in META_FILES]
        nodes = []
        for page_path in pages:
            node_id = _node_id(page_path, self.wiki_dir)
            ptype = _page_type(page_path, self.wiki_dir)
            label = _node_label(page_path)
            nodes.append({
                "id": node_id,
                "label": label,
                "type": ptype,
                "color": TYPE_COLORS.get(ptype, TYPE_COLORS["unknown"]),
                "path": str(page_path.relative_to(self.wiki_dir)).replace("\\", "/"),
            })
        nodes.sort(key=lambda n: n["id"])

        # Pass 3: 社区检测
        communities = self.detect_communities(nodes, all_edges)

        # 将社区信息注入节点
        for node in nodes:
            comm = communities.get(node["id"], {})
            node["community"] = comm.get("community", -1)
            node["communityColor"] = comm.get("color", TYPE_COLORS["unknown"])

        # 统计
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        result = {
            "nodes": nodes,
            "edges": all_edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(all_edges),
                "extracted_edges": len(extracted_edges),
                "inferred_edges": len(inferred_edges),
                "community_count": len(
                    set(c["community"] for c in communities.values())
                ),
                "build_time_seconds": round(elapsed, 2),
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # 导出 G6 JSON
        output_path = self.graph_dir / "graph.json"
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"图谱构建完成: {result['stats']}")

        return result

    def load(self) -> Optional[dict]:
        """加载已构建的图谱数据。"""
        json_path = self.graph_dir / "graph.json"
        if json_path.exists():
            return json.loads(json_path.read_text(encoding="utf-8"))
        return None

    def stats(self) -> dict:
        """获取图谱统计信息。"""
        data = self.load()
        if data:
            return data["stats"]
        return {"node_count": 0, "edge_count": 0}
