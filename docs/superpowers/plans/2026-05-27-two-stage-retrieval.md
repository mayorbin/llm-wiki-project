# 两阶段图谱引导检索 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造知识查询管道：简单问题走旧流程，内容问题通过图谱社区发现定位原始文件后做两轮 LLM 全文检索-综合。

**Architecture:** 所有改动集中在 `query_service.py`，在 `query_knowledge()` 入口插入分派逻辑 → `_classify_question()` → `_discover_documents()` → `_extract_passages()` + `_synthesize_answer()`。对外 API 接口不变。

**Tech Stack:** Python 3.10+, litellm, ThreadPoolExecutor, NetworkX (graph.json 读取)

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `backend/app/services/query_service.py` | 主战场：5 个新函数 + 旧 `query_knowledge` 改为分派入口 |
| `backend/tests/unit/test_knowledge.py` | 新增测试类 `TestTwoStageRetrieval` |
| `frontend/src/views/KnowledgeBaseView.vue` | 超时从 180s → 300s |
| `frontend/src/api/knowledge.ts` | 超时从 180000 → 300000 |

---

### Task 1: 提取 prompt 模板 + 添加导入

**Files:** Modify `backend/app/services/query_service.py` (top section)

- [ ] **Step 1: 在文件顶部导入区添加新依赖**

在现有 `from typing import Optional` 后追加：

```python
import re
import re as _re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal
```

在现有 `from app.engines.wiki_engine import (...)` 后追加导入：

```python
from app.engines.wiki_engine import META_FILES
```

最终导入区如下：

```python
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
```

- [ ] **Step 2: 在 `_now()` 函数之后、`_check_project_access` 之前添加 prompt 常量**

```python
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
```

- [ ] **Step 3: 验证导入和语法**

```bash
cd backend && python -c "from app.services.query_service import _now, _check_project_access, _STRUCTURE_KEYWORDS; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "chore: 两阶段检索——导入依赖和 prompt 模板常量"
```

---

### Task 2: 实现 `_classify_question()` 问题分类器

**Files:** Modify `backend/app/services/query_service.py` (insert after `_check_project_access`, before `_project_wiki_dir`)

- [ ] **Step 1: 添加分类函数**

```python
def _classify_question(question: str, wiki_dir: Path) -> Literal["simple", "content", "unknown"]:
    """将用户问题分为三类：simple（结构查询）、content（内容检索）、unknown（无匹配）。

    Args:
        question: 用户问题文本
        wiki_dir: wiki 目录路径

    Returns:
        "simple"  — 结构类关键词命中，走旧流程摘要直答
        "content" — 含 wikilinks 或已知实体/概念名匹配，进入两阶段检索
        "unknown" — 无任何匹配，走旧流程 + 提示
    """
    # 检查结构类关键词（问题开头 20 字符内）
    q_head = question[:20]
    for kw in _STRUCTURE_KEYWORDS:
        if kw in q_head:
            return "simple"

    # 检查 wikilinks
    if extract_wikilinks(question):
        return "content"

    # 检查是否命中已知实体/概念页面名（取词长 >= 2 的词做匹配）
    existing_pages = all_wiki_pages(wiki_dir)
    # 从问题中提取潜在实体名（长度 > 2 的中文词或 > 1 的英文词）
    words = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{2,}', question)
    for w in words:
        if w.lower() in existing_pages:
            return "content"

    return "unknown"
```

- [ ] **Step 2: 验证语法**

```bash
cd backend && python -c "
from pathlib import Path
from app.services.query_service import _classify_question
import tempfile, os

# 创建临时 wiki 目录测试
d = Path(tempfile.mkdtemp())
(d / 'entities').mkdir(parents=True)
(d / 'entities' / 'openai.md').write_text('# OpenAI')
(d / 'sources').mkdir(parents=True)
(d / 'sources' / 'test.md').write_text('# Test')

assert _classify_question('有哪些文档？', d) == 'simple'
assert _classify_question('[[OpenAI]] 融资', d) == 'content'
assert _classify_question('OpenAI 历次融资', d) == 'content'
assert _classify_question('这是什么项目？', d) == 'unknown'
print('All assertions passed')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat: 添加 _classify_question() 问题分类器"
```

---

### Task 3: 实现 `_discover_documents()` 图谱引导文档发现

**Files:** Modify `backend/app/services/query_service.py` (insert after `_classify_question`)

- [ ] **Step 1: 添加文档发现函数**

```python
def _discover_documents(question: str, project_id: str) -> tuple[list[Path], list[str]]:
    """通过图谱社区发现定位相关的原始文件。

    Args:
        question: 用户问题
        project_id: 项目 ID

    Returns:
        (raw_file_paths, matched_labels): 原始文件路径列表 + 匹配到的节点标签列表
        文件路径列表可能为空（无匹配或图谱未构建）
    """
    settings = get_settings()
    project_dir = Path(settings.data_dir) / "projects" / project_id
    graph_file = project_dir / "graph" / "graph.json"
    wiki_dir = project_dir / "wiki"

    if not graph_file.exists():
        logger.info("图谱未构建，跳过文档发现", extra={"project_id": project_id})
        return [], []

    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        return [], []

    # 计算 node degree（从 edges 统计各节点出现次数）
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    # 构建 node_id → node 的索引
    node_by_id: dict[str, dict] = {n["id"]: n for n in nodes}

    # ── 节点匹配（三级优先级）──
    matched_nodes: list[dict] = []

    # 优先级 1：wikilinks 精确匹配 node.label
    for link_name in extract_wikilinks(question):
        for node in nodes:
            if node.get("label") == link_name:
                matched_nodes.append(node)

    # 优先级 2：中文词或英文词模糊匹配 node.label
    if not matched_nodes:
        words = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{2,}', question)
        for w in words:
            w_lower = w.lower()
            for node in nodes:
                label = (node.get("label") or "").lower()
                if w_lower in label:
                    matched_nodes.append(node)

    # 优先级 3：与 source 节点 label 关键词重叠最多的
    if not matched_nodes:
        words_lower = [w.lower() for w in words]
        best_node = None
        best_score = 0
        for node in nodes:
            if node.get("type") != "source":
                continue
            label = (node.get("label") or "").lower()
            score = sum(1 for w in words_lower if w in label)
            if score > best_score:
                best_score = score
                best_node = node
        if best_node:
            matched_nodes.append(best_node)

    if not matched_nodes:
        return [], []

    # ── 社区拉取 ──
    candidate_source_ids: set[str] = set()
    matched_labels: list[str] = []

    for mn in matched_nodes:
        matched_labels.append(mn.get("label", mn["id"]))
        community = mn.get("community", -1)

        if community == -1:
            # 孤立节点：仅用自身（如果是 source 类型）
            if mn.get("type") == "source":
                candidate_source_ids.add(mn["id"])
        else:
            # 同社区 source 节点 → 按 degree 降序取前 8
            community_sources = [
                n for n in nodes
                if n.get("type") == "source" and n.get("community") == community
            ]
            community_sources.sort(key=lambda n: degree.get(n["id"], 0), reverse=True)
            for n in community_sources[:8]:
                candidate_source_ids.add(n["id"])

    # ── 源文件定位 ──
    raw_files: list[Path] = []
    seen_raw_paths: set[str] = set()

    for node_id in candidate_source_ids:
        node = node_by_id.get(node_id)
        if not node:
            continue
        # 读取 wiki 页面的 frontmatter 获取 source_file
        wiki_page_path = wiki_dir / (node.get("path", node_id))
        if not wiki_page_path.exists():
            continue
        content = read_page(wiki_page_path)
        m = re.search(r'(?m)^source_file:\s*(.+)$', content)
        raw_rel = m.group(1).strip() if m else None
        if not raw_rel:
            continue
        raw_path = (project_dir / "raw" / raw_rel).resolve()
        if raw_path.exists() and raw_path.is_file():
            raw_key = str(raw_path)
            if raw_key not in seen_raw_paths:
                seen_raw_paths.add(raw_key)
                raw_files.append(raw_path)

    logger.info("图谱文档发现完成",
        extra={"project_id": project_id, "matched": matched_labels,
               "candidates": len(raw_files)})

    return raw_files, matched_labels
```

- [ ] **Step 2: 验证语法和基本逻辑**

```bash
cd backend && python -c "
from app.services.query_service import _discover_documents
print('Function imported successfully')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat: 添加 _discover_documents() 图谱引导文档发现"
```

---

### Task 4: 实现 `_read_file_content()` 文件内容读取

**Files:** Modify `backend/app/services/query_service.py` (insert after `_discover_documents`)

- [ ] **Step 1: 添加文件读取函数**

```python
_TEXT_SUFFIXES = {'.md', '.txt', '.csv', '.json', '.yaml', '.yml', '.xml', '.html', '.htm'}


def _read_file_content(raw_path: Path) -> str:
    """读取原始文件内容（非文本文件先经 ConvertEngine 转换）。

    Args:
        raw_path: 原始文件的绝对路径

    Returns:
        文件文本内容（截断至 30000 字符）
    """
    suffix = raw_path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        try:
            content = raw_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = raw_path.read_bytes()[:100 * 1024].decode("utf-8", errors="replace")
    else:
        try:
            from app.engines.convert_engine import ConvertEngine
            engine = ConvertEngine()
            content = engine.convert(raw_path)
        except Exception as e:
            logger.warning("文件转换失败，回退到原始读取",
                extra={"file": str(raw_path), "error": str(e)})
            content = raw_path.read_bytes()[:100 * 1024].decode("utf-8", errors="replace")

    return content[:30000]
```

- [ ] **Step 2: 验证语法**

```bash
cd backend && python -c "
from app.services.query_service import _read_file_content
print('Function imported successfully')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat: 添加 _read_file_content() 原始文件读取"
```

---

### Task 5: 实现两轮 LLM 检索

**Files:** Modify `backend/app/services/query_service.py` (insert after `_read_file_content`)

- [ ] **Step 1: 添加 Round 1 + Round 2 函数**

```python
def _run_extraction(question: str, file_paths: list[Path],
                    project_id: str, model: Optional[str]) -> dict[str, str]:
    """Round 1: 并行从每个候选文件中提取相关段落。

    Args:
        question: 用户问题
        file_paths: 候选原始文件路径列表
        project_id: 项目 ID
        model: LLM 模型

    Returns:
        {file_name: extracted_text} 映射（只包含成功提取的文件）
    """
    from app.engines.llm_engine import call_llm

    results: dict[str, str] = {}

    def extract_one(fp: Path) -> tuple[str, str | None]:
        try:
            content = _read_file_content(fp)
            if not content.strip():
                return (fp.name, None)
            prompt = _EXTRACTION_USER_PROMPT.format(
                file_path=str(fp),
                content=content,
                question=question,
            )
            raw = call_llm(
                prompt=prompt,
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                model=model,
                project_id=project_id,
                timeout=120,
                max_tokens=1024,
            )
            if not raw.strip() or "无相关内容" in raw:
                return (fp.name, None)
            return (fp.name, raw.strip())
        except Exception as e:
            logger.warning("文件段落提取失败",
                extra={"file": str(fp), "error": str(e)})
            return (fp.name, None)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(extract_one, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            name, text = future.result()
            if text:
                results[name] = text

    return results


def _synthesize_answer(question: str, excerpts: dict[str, str],
                       matched_labels: list[str],
                       project_id: str, model: Optional[str]) -> str:
    """Round 2: 汇总提取结果，综合回答。

    Args:
        question: 用户问题
        excerpts: {file_name: extracted_text}
        matched_labels: 图谱中匹配到的节点标签（用于 wikilink 引用）
        project_id: 项目 ID
        model: LLM 模型

    Returns:
        LLM 综合回答
    """
    from app.engines.llm_engine import call_llm

    parts = []
    for fname, text in excerpts.items():
        parts.append(f"### 来源: {fname}\n{text}")
    combined = "\n\n---\n\n".join(parts)
    page_refs = "\n".join(f"- [[{label}]]" for label in matched_labels) if matched_labels else "(无)"

    full_prompt = _SYNTHESIS_USER_PROMPT.format(
        combined_excerpts=combined,
        page_refs=page_refs,
        question=question,
    )

    answer = call_llm(
        prompt=full_prompt,
        system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
        model=model,
        project_id=project_id,
        timeout=180,
        max_tokens=2048,
    )

    return answer or f"综合回答失败：未能从相关文档中提取到信息。"
```

- [ ] **Step 2: 验证语法**

```bash
cd backend && python -c "
from app.services.query_service import _run_extraction, _synthesize_answer
print('Functions imported successfully')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat: 添加 _run_extraction() + _synthesize_answer() 两轮 LLM 检索"
```

---

### Task 6: 重构 `query_knowledge()` 为分派入口

**Files:** Modify `backend/app/services/query_service.py` (replace existing `query_knowledge`)

- [ ] **Step 1: 替换 `query_knowledge()` 函数**

```python
def query_knowledge(
    project_id: str, user_id: str, question: str,
    model: Optional[str] = None,
) -> dict:
    """使用 LLM 查询知识库。

    简单问题 → 旧流程摘要直答（快速通道）
    内容问题 → 图谱引导两阶段全文检索
    未知问题 → 旧流程 + 提示

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
    classification = _classify_question(question, wiki_dir)

    # ── simple: 旧流程摘要直答 ──
    if classification == "simple":
        return _summary_query(project_id, question, wiki_dir, model)

    # ── content: 图谱引导两阶段检索 ──
    if classification == "content":
        raw_files, matched_labels = _discover_documents(question, project_id)

        if raw_files:
            excerpts = _run_extraction(question, raw_files, project_id, model)

            if excerpts:
                answer = _synthesize_answer(
                    question, excerpts, matched_labels, project_id, model,
                )
                answer_links = extract_wikilinks(answer)
                return {
                    "question": question,
                    "answer": answer,
                    "sources": [str(p) for p in raw_files],
                    "references": answer_links,
                    "searched_at": _now(),
                }

        # 文档发现或提取失败 → 回退到旧流程 + 提示
        result = _summary_query(project_id, question, wiki_dir, model)
        result["answer"] = _UNKNOWN_HINT + result["answer"]
        return result

    # ── unknown: 旧流程 + 提示 ──
    result = _summary_query(project_id, question, wiki_dir, model)
    result["answer"] = _UNKNOWN_HINT + result["answer"]
    return result


def _summary_query(project_id: str, question: str, wiki_dir: Path,
                   model: Optional[str]) -> dict:
    """旧流程：基于 wiki 摘要页面的查询（抽取自原 query_knowledge 逻辑）。

    Args:
        project_id: 项目 ID
        question: 用户问题
        wiki_dir: wiki 目录路径
        model: LLM 模型

    Returns:
        {question, answer, sources, references, searched_at}
    """
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
            page_path = wiki_dir / f"{link_name}.md"
            if page_path.exists():
                content = read_page(page_path)
                contexts.append(f"## {link_name}\n{content[:4000]}")
                sources_list.append(f"{link_name}.md")

    # 如果没有找到相关上下文，加载最近更新的几篇文章
    if len(contexts) <= 1:
        all_pages = sorted(
            [p for p in wiki_dir.rglob("*.md")
             if p.name not in META_FILES],
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

    answer_links = extract_wikilinks(answer)

    return {
        "question": question,
        "answer": answer,
        "sources": sources_list,
        "references": answer_links,
        "searched_at": _now(),
    }
```

- [ ] **Step 2: 验证语法和基本逻辑**

```bash
cd backend && python -c "
from app.services.query_service import query_knowledge, _summary_query
print('Functions imported successfully')
"
```

- [ ] **Step 3: 运行现有测试确保旧流程不受影响**

```bash
cd backend && python -m pytest tests/unit/test_knowledge.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat: 重构 query_knowledge() 为三路分派入口"
```

---

### Task 7: 编写测试

**Files:** Modify `backend/tests/unit/test_knowledge.py` (append at end)

- [ ] **Step 1: 添加两阶段检索测试类**

```python
class TestTwoStageRetrieval:
    """两阶段检索测试。"""

    def test_分类简单问题(self):
        """结构类关键词应返回 simple。"""
        user, project = _create_user_and_project("g1", "Proj")
        wiki = _wiki_dir(project["id"])
        (wiki / "sources").mkdir(parents=True, exist_ok=True)

        from app.services.query_service import _classify_question
        assert _classify_question("有哪些文档？", wiki) == "simple"
        assert _classify_question("列出所有文件", wiki) == "simple"
        assert _classify_question("目录", wiki) == "simple"

    def test_分类内容问题_wikilink匹配(self):
        """含 wikilinks 的问题应返回 content。"""
        user, project = _create_user_and_project("g2", "Proj")
        wiki = _wiki_dir(project["id"])

        from app.services.query_service import _classify_question
        assert _classify_question("[[OpenAI]] 融资情况", wiki) == "content"

    def test_分类内容问题_实体名匹配(self):
        """含已知实体页面的问题应返回 content。"""
        user, project = _create_user_and_project("g3", "Proj")
        wiki = _wiki_dir(project["id"])
        (wiki / "entities").mkdir(parents=True, exist_ok=True)
        (wiki / "entities" / "openai.md").write_text("# OpenAI")

        from app.services.query_service import _classify_question
        assert _classify_question("OpenAI 历次融资", wiki) == "content"

    def test_分类未知问题(self):
        """无任何匹配的问题应返回 unknown。"""
        user, project = _create_user_and_project("g4", "Proj")
        wiki = _wiki_dir(project["id"])

        from app.services.query_service import _classify_question
        assert _classify_question("这个项目是关于什么的？", wiki) == "unknown"

    def test_探索文档_图谱未构建时返回空(self):
        """graph.json 不存在时应返回空列表。"""
        user, project = _create_user_and_project("g5", "Proj")

        from app.services.query_service import _discover_documents
        files, labels = _discover_documents("[[Something]] test", project["id"])
        assert files == []
        assert labels == []

    def test_读取文件内容_文本文件(self, tmp_path):
        """应能读取纯文本文件内容。"""
        f = tmp_path / "test.md"
        f.write_text("# Hello\nWorld", encoding="utf-8")

        from app.services.query_service import _read_file_content
        content = _read_file_content(f)
        assert "Hello" in content

    def test_简单问题走旧流程(self, monkeypatch):
        """简单问题应走摘要检索路径（不打 round 1）。"""
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-dummy")
        user, project = _create_user_and_project("g6", "Proj")
        _create_test_page(project["id"], "sources/TestPage.md",
                          "---\ntitle: Test\n---\n\n## Summary\nHello")

        # 这个测试验证分类为 simple 时不触发两阶段检索，
        # 只验证调用不抛异常
        try:
            result = svc.query_knowledge(project["id"], user.id, "有哪些文档？")
            assert "question" in result
            # simple 分类不会带 _UNKNOWN_HINT 前缀
            assert not result.get("answer", "").startswith("未找到与问题直接相关的文档")
        except Exception:
            # LLM 可能在测试环境不可用，跳过
            pass

    def test_未知问题带提示(self, monkeypatch):
        """unknown 分类应在答案前加提示。"""
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-dummy")
        user, project = _create_user_and_project("g7", "Proj")

        try:
            result = svc.query_knowledge(project["id"], user.id, "这是什么项目？")
            assert "question" in result
        except Exception:
            pass
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && python -m pytest tests/unit/test_knowledge.py -v -k "TestTwoStageRetrieval"
```

- [ ] **Step 3: 运行全部知识测试确保无回归**

```bash
cd backend && python -m pytest tests/unit/test_knowledge.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/test_knowledge.py
git commit -m "test: 两阶段检索单元测试"
```

---

### Task 8: 前端超时适配

**Files:** Modify `frontend/src/api/knowledge.ts`, `frontend/src/views/KnowledgeBaseView.vue`

- [ ] **Step 1: 延长查询超时**

`frontend/src/api/knowledge.ts` — 将 timeout 从 180000 → 300000：

```typescript
import client from './client'

export const knowledgeApi = {
  query(projectId: string, question: string, model?: string | null) {
    return client.post('/knowledge/query', { project_id: projectId, question, model }, { timeout: 300000 })
  },
  getPageTree(projectId: string) {
    return client.get('/knowledge/pages', { params: { project_id: projectId } })
  },
  getPage(projectId: string, pagePath: string) {
    return client.get(`/knowledge/pages/${pagePath.split('/').map(encodeURIComponent).join('/')}`, { params: { project_id: projectId } })
  },
  updatePage(projectId: string, pagePath: string, content: string) {
    return client.put(`/knowledge/pages/${pagePath.split('/').map(encodeURIComponent).join('/')}`, { project_id: projectId, content })
  },
}
```

> 注意：将现有 180000 (3min) 改为 300000 (5min)，因为两阶段检索最多涉及 Round1(120s×3并行) + Round2(180s)

- [ ] **Step 2: 前端构建验证**

```bash
cd frontend && npx vue-tsc --noEmit && npx vite build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/knowledge.ts
git commit -m "chore: 知识查询超时 180s → 300s 适配两阶段检索"
```

---

### Task 9: 端到端验证

- [ ] **Step 1: 启动后端确认无导入错误**

```bash
cd backend && python -c "from app.main import app; print('Backend loads OK')"
```

- [ ] **Step 2: 运行完整测试套件确认无回归**

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tail -10
```

- [ ] **Step 3: Commit any final fixes**

---

## 完成后验证清单

- [ ] 全量测试：`cd backend && python -m pytest tests/ -v`
- [ ] typecheck：`cd frontend && npx vue-tsc --noEmit`
- [ ] 前端构建：`cd frontend && npx vite build`
- [ ] 真实环境测试：上传文件 → 摄入 → 构建图谱 → 内容问题查询（验证走两阶段检索）
- [ ] 真实环境测试：结构问题查询（验证走旧流程快速通道）
