# 两阶段图谱引导检索 — 设计规格

**日期**: 2026-05-27
**状态**: 已审核（v1.1）

## 问题

当前知识摄入生成摘要 wiki 页面，知识检索也仅基于这些摘要回答。原始文件的完整内容在检索阶段完全没有被利用。当用户问"OpenAI 历次融资情况"时，即使原始 PDF 中有完整的融资表格，答复也只能基于几百字的摘要——信息大量丢失。

## 目标

改造查询管道为两阶段架构：

1. **图谱引导文档发现**：利用已有 knowledge graph 的社区结构，从问题出发找到同一社区的相关源文档
2. **全文 LLM 检索**：两轮 LLM 调用——（Round 1）从每个候选文档中精确提取相关段落，（Round 2）汇总精华段落后综合回答

同时保留简单问题（"有哪些文档？"）走旧流程作为快速通道。

## 架构

```
用户提问
    │
    ▼
┌─ Phase 0: 问题分类 ─────────────────────────────────────┐
│  三类输出：                                               │
│    "simple"  — 结构类关键词命中 → 旧流程摘要直答             │
│    "content" — 含 wikilinks 或实体/概念名 → 进入 Phase 1    │
│    "unknown" — 无任何匹配 → 旧流程 + 提示"未找到相关文档"     │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Phase 1: 图谱引导文档发现 ───────────────────────────────┐
│  1. 从问题中提取 [[wikilinks]] 文本                         │
│  2. 加载 graph.json（已有 → 不重新构建）                     │
│  3. 查找匹配节点 → 获取其 community 编号                     │
│  4. 拉取同社区内 type=source 节点（按 degree 降序，≤8 个）    │
│  5. 读取 wiki 页面的 source_file frontmatter                 │
│  6. 映射到 raw/ 目录下的原始文件（去重）                      │
│                                                          │
│  输出: 原始文件路径列表（通常 3-8 个）                        │
│  退化: 无匹配节点 → 回退到旧流程                              │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Phase 2: 两轮 LLM 检索-综合 ────────────────────────────┐
│  Round 1（并行，ThreadPoolExecutor max_workers=3）:         │
│    非 .md/.txt 文件先经 ConvertEngine 转文本                 │
│    每个候选文件调用 LLM，提取与问题最相关的段落                │
│    prompt 要求结构化输出：原文引用 + 来源位置                  │
│    文件内容上限 30000 字符                                  │
│    输出: 每文件 ≤800 字的结构化精华片段                       │
│                                                          │
│  Round 2:                                                 │
│    汇总所有 Round 1 精华片段 + 用户问题                       │
│    LLM 综合回答（带 [[wikilink]] 引用和精确来源）              │
│    输出: 完整答案 + 引用源文件列表                            │
└────────────────────────────────────────────────────────┘
```

## Phase 0 细节

### 问题分类规则

`_classify_question(question, wiki_dir) → Literal["simple", "content", "unknown"]`

| 类别 | 判定条件 | 处理方式 | 示例 |
|------|----------|---------|------|
| `simple` | 以结构类关键词开头/包含 | 旧流程摘要直答 | "有哪些文档"、"目录"、"统计" |
| `content` | 含 wikilinks 或已知实体/概念名匹配 | 进入 Phase 1 | "OpenAI 融资情况" |
| `unknown` | 无 wikilinks 且无实体/概念匹配 | 旧流程 + 前端提示 | "这个项目是关于什么的？" |

结构类关键词列表：`["有哪些文档", "多少篇", "列出", "目录", "概述", "总共", "几个", "统计", "索引", "汇总"]`

### 实现备注

- 正则匹配结构关键词（问题开头 20 字符内检查）
- 用 `extract_wikilinks()` + `all_wiki_pages()` 检查实体/概念命中
- `unknown` 类返回时在 `answer` 前附加提示"未找到与问题直接相关的文档，以下为知识库概览："

## Phase 1 细节

### 图谱节点匹配

从 `graph.json` 的 `nodes` 数组中查找匹配：

- **优先级 1**：wikilink 文本精确匹配 `node.label`（节点标签来自页面标题）
- **优先级 2**：问题中的中文词组（长度 > 2）或英文单词模糊匹配 `node.label`（子串匹配，case-insensitive）
- **优先级 3**：如果以上都没匹配到，选择与问题关键词（切词后）重叠最多的 source 节点

**注意**：`node.id` 是路径格式（`sources/kebab-case-slug`），其 stem 与 wikilink 的中文显示名不匹配，因此仅用 `node.label` 作为匹配目标。

### 社区拉取与排序

获取匹配节点的 `community` 编号 → 从 `nodes` 中筛选所有 `community` 相同且 `type == "source"` 的节点 → 按 degree（关联边数量）降序排列 → 取前 8 个。

孤立节点（community = -1）：仅用该节点自己的 `source_file`。

选择策略依据：degree 越高的 source 节点在知识网络中连接越丰富，越可能包含与问题相关的信息。

### 源文件定位

对每个 source 节点：
1. 读取 `wiki/<node.path>` 获取 frontmatter 中的 `source_file`（含子目录路径，如 `AI/report.pdf`）
2. 构造 `raw/<source_file>` 路径并验证文件存在
3. 去重（同一 `source_file` 可能被多个 wiki 页面引用）

### 实现

`_discover_documents(question, project_id) → list[Path]`

- 调用 `graph_service.get_graph_data()` 获取现有图谱数据
- 返回去重后的原始文件绝对路径列表

## Phase 2 细节

### 文件内容读取

非纯文本文件（`.md`、`.txt` 以外）在 Round 1 之前先经 `ConvertEngine` 转换为文本：

```python
if raw_path.suffix not in ('.md', '.txt', '.csv', '.json', '.yaml', '.yml', '.xml', '.html'):
    content_str = ConvertEngine().convert(raw_path)
else:
    content_str = raw_path.read_text(encoding='utf-8')
```

`ConvertEngine` 已在 `task_queue.py::_ingest_single_file` 中使用，直接复用。

### Round 1: 段落提取

每个候选文件独立调用 LLM，通过 `ThreadPoolExecutor(max_workers=3)` + `as_completed` 并行执行（与 `task_queue.py:318` 模式一致，`call_llm` 是同步函数，无需 `asyncio`）。

**System prompt**：
```
你是一个文本检索助手。从以下文档中提取与用户问题最相关的段落。
保留原始数据和数值。如果文档中确实没有相关信息，返回空。
```

**User prompt**：
```
文档: {file_path}
内容:
{content[:30000]}

问题: {question}

请提取与问题最相关的段落，按以下格式返回：
---
相关段落: <原文引用>
来源位置: <段落所在章节或行号范围>
---
（可返回多个段落块。如果文档不包含相关信息，返回"无相关内容"。
保留所有关键数据和表格信息。总计不超过 800 字。）
```

**错误处理**：
- 单个文件提取失败 → 跳过，继续处理其他文件
- 文件读取/转换失败（编码、格式不支持等）→ 跳过
- 所有文件均失败 → 回退到旧流程摘要检索
- LLM 返回空或 "无相关内容" → 正常跳过，不计入失败

### Round 2: 综合回答

**system_prompt**：
```
根据以下从多个文档中提取的相关段落，综合回答用户问题。
回答中使用 [[页面名]] 格式引用来源。每个关键事实附上来源标注。
中文回答。如果段落信息不足以回答问题，诚实说明。
```

**user_prompt**：
```
相关段落:
{combined_excerpts}

问题: {question}

综合以上信息回答（使用 [[wikilinks]] 引用来源）：
```

## 数据流

```
query_knowledge(question)
  │
  ├─ _classify_question(question) == "simple"
  │    └─ 现有旧流程（摘要检索）→ 返回
  │
  ├─ _classify_question(question) == "unknown"
  │    └─ 现有旧流程（摘要检索）+ 提示信息 → 返回
  │
  └─ _classify_question(question) == "content"
       │
       ├─ _discover_documents(question)
       │    └─ graph_service.get_graph_data()
       │    └─ 节点匹配 + 社区拉取（按 degree 降序，≤8）
       │    └─ source_file 定位 raw 文件
       │    └─ 非文本文件经 ConvertEngine 转文本
       │
       ├─ documents 为空 → 回退旧流程 + 提示
       │
       └─ _two_stage_retrieval(question, documents)
            │
            ├─ Round 1: ThreadPoolExecutor(max_workers=3) 并行
            │    └─ call_llm(extraction_prompt) per file
            │    └─ 结构化输出解析
            │
            ├─ Round 1 全部失败 → 回退旧流程 + 提示
            │
            └─ Round 2: call_llm(synthesis_prompt)
                 └─ 返回 { answer, sources, references }
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/query_service.py` | 主要改动：`_classify_question()`、`_discover_documents()`、`_extract_relevant_passages()`、`_synthesize_answer()`、修改 `query_knowledge()` 入口。Prompt 模板提取为模块级常量 |
| `backend/app/api/knowledge.py` | 无需改动（`query_knowledge` 对外接口不变） |
| `backend/app/services/graph_service.py` | 可能需要加一个 `get_community_sources()` 辅助方法 |
| `backend/tests/unit/test_knowledge.py` | 新增两阶段检索的测试用例 |
| `frontend/src/views/KnowledgeBaseView.vue` | 查询超时可能需要从 180s 延长（取决于文件数量），`unknown` 分类返回时展示提示 |

## 边界条件

- **图谱未构建**：`graph.json` 不存在 → 退回到旧流程
- **社区为空**：匹配到节点但 community 为 -1（孤立节点）→ 仅用该节点自己的 `source_file`
- **社区过大**：同社区 source 节点 > 8 → 按 degree 降序取前 8
- **超大文件**：文件内容截断至 30000 字符 / Round 1
- **非文本文件**：Round 1 前经 `ConvertEngine` 转文本（复用摄入管道的转换逻辑）
- **LLM 超时**：Round 1 单文件超时 120s，Round 2 超时 180s
- **并发限制**：Round 1 最多 3 个并行 LLM 调用，使用 `ThreadPoolExecutor`（非 `asyncio`，与 `task_queue.py` 一致）
- **token 成本**：Round 1 输入 90K-240K 字符（3-8 文件 × 30K），按 DeepSeek 定价单次查询约 ¥0.3-1.0。这是全文检索的固有成本

## 不在此范围

- 图谱增量更新（不在本次范围）
- 搜索 UI 改造（前端暂时不变，仅查询超时和 `unknown` 提示做最小适配）
- 向量化检索 / embedding（本次用图谱社区 + LLM 提取，未来可选加 RAG）
- Round 1 结果缓存（后续迭代）
- 引入异步 web 框架（查询保持同步模式，与现有 API 一致）
