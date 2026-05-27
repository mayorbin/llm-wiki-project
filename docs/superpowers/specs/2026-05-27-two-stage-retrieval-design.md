# 两阶段图谱引导检索 — 设计规格

**日期**: 2026-05-27
**状态**: 待审核

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
┌─ Phase 0: 问题分类 ─────────────────────────────────┐
│  判定规则：                                            │
│    简单问题（结构类关键词 OR 无实体/概念命中）→ 旧流程摘要直答  │
│    内容问题（含 wikilinks OR 实体/概念关键词）→ 进入 Phase 1 │
└────────────────────────────────────────────────────┘
    │
    ▼
┌─ Phase 1: 图谱引导文档发现 ────────────────────────────┐
│  1. 从问题中提取 [[wikilinks]] 文本                      │
│  2. 加载 graph.json（已有 → 不重新构建）                    │
│  3. 查找匹配节点 → 获取其 community 编号                    │
│  4. 拉取同社区内所有 type=source 的节点                    │
│  5. 读取 wiki 页面的 source_file frontmatter              │
│  6. 映射到 raw/ 目录下的原始文件（去重）                     │
│                                                       │
│  输出: 原始文件路径列表（通常 3-8 个）                      │
│  退化: 无匹配节点 → 回退到旧流程                            │
└────────────────────────────────────────────────────┘
    │
    ▼
┌─ Phase 2: 两轮 LLM 检索-综合 ─────────────────────────┐
│  Round 1（并行，max_workers=3）:                         │
│    每个候选文件调用 LLM，system_prompt:                    │
│    "从以下文档中提取与用户问题最相关的段落……"                 │
│    读取文件全文（上限 30000 字符）                          │
│    输出: 每文件 ≤800 字的相关摘要                          │
│                                                       │
│  Round 2:                                              │
│    汇总所有 Round 1 摘要 + 用户问题                        │
│    LLM 综合回答（带 [[wikilink]] 引用）                    │
│    输出: 完整答案 + 引用源文件列表                          │
└────────────────────────────────────────────────────┘
```

## Phase 0 细节

### 简单问题判定规则

问题满足以下任一条件 → 简单问题 → 走旧流程摘要直答：

| 规则 | 示例 |
|------|------|
| 以结构类关键词开头/包含 | "有哪些文档"、"多少篇"、"列出"、"目录"、"概述"、"总共" |
| 问题 < 10 字符 | "文档列表" |
| 无 wikilinks 且无已知实体/概念名匹配 | "这个项目是关于什么的？" |

### 实现

`_classify_question(question, wiki_dir) → Literal["simple", "content"]`

- 正则匹配结构关键词
- 用 `extract_wikilinks()` 和 `all_wiki_pages()` 检查是否有实体/概念匹配
- 返回分类结果

## Phase 1 细节

### 图谱节点匹配

从 `graph.json` 的 `nodes` 数组中查找匹配：

- **优先级 1**：wikilink 文本精确匹配 `node.label` 或 `node.id` 的 stem
- **优先级 2**：问题中的关键词（长度 > 2 的中文/英文词组）匹配 `node.label`
- **优先级 3**：如果以上都没匹配到，选择与问题关键词重叠最多的 source 节点

### 社区拉取

获取匹配节点的 `community` 编号 → 从 `nodes` 中筛选所有 `community` 相同且 `type == "source"` 的节点 → 最多取 8 个。

### 源文件定位

对每个 source 节点：
1. 读取 `wiki/<node.path>` 获取 frontmatter 中的 `source_file`
2. 验证 `raw/<source_file>` 是否存在
3. 去重（同一 source_file 可能被多个 wiki 页面引用）

### 实现

`_discover_documents(question, project_id) → list[Path]`

- 调用 `graph_service.get_graph_data()` 获取现有图谱数据
- 返回去重后的原始文件绝对路径列表

## Phase 2 细节

### Round 1: 段落提取

每个候选文件独立调用 LLM：

```
system: "你是一个文本检索助手。从以下文档中提取与用户问题最相关的段落。
   保留原始数据和数值。如果文档中确实没有相关信息，返回空。"
    
prompt: "文档: {file_path}
   内容: {content[:30000]}
   问题: {question}
   提取与问题最相关的段落（不超过 800 字，保留关键数据和表格信息）:"
```

并行执行通过 `asyncio.to_thread` + `ThreadPoolExecutor(max_workers=3)` 实现。

**错误处理**：
- 单个文件提取失败 → 跳过，不影响其他文件
- 文件读取失败（编码等）→ 跳过
- 所有文件均失败 → 回退到旧流程摘要检索

### Round 2: 综合回答

```
system: "根据以下从多个文档中提取的相关段落，综合回答用户问题。
   回答中使用 [[页面名]] 引用来源。中文回答。"

prompt: "相关段落:
   {combined_excerpts}
   问题: {question}
   综合以上信息回答:"
```

## 数据流

```
query_knowledge(question)
  │
  ├─ _classify_question(question) == "simple"
  │    └─ 现有旧流程（摘要检索）→ 返回
  │
  └─ _classify_question(question) == "content"
       │
       ├─ _discover_documents(question)
       │    └─ graph_service.get_graph_data()
       │    └─ 节点匹配 + 社区拉取
       │    └─ source_file 定位 raw 文件
       │
       ├─ documents 为空 → 回退旧流程
       │
       └─ _two_stage_retrieval(question, documents)
            │
            ├─ Round 1: asyncio.to_thread × N（并行）
            │    └─ call_llm(extraction_prompt) per file
            │
            ├─ Round 1 全部失败 → 回退旧流程
            │
            └─ Round 2: call_llm(synthesis_prompt)
                 └─ 返回 { answer, sources, references }
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/query_service.py` | 主要改动：`_classify_question()`、`_discover_documents()`、`_extract_relevant_passages()`、`_synthesize_answer()`、修改 `query_knowledge()` 入口 |
| `backend/app/api/knowledge.py` | 无需改动（`query_knowledge` 对外接口不变） |
| `backend/app/services/graph_service.py` | 可能需要加一个 `get_community_sources()` 辅助方法 |
| `backend/tests/unit/test_knowledge.py` | 新增两阶段检索的测试用例 |

## 边界条件

- **图谱未构建**：`graph.json` 不存在 → 退回到旧流程
- **社区为空**：匹配到节点但 community 为 -1（孤立节点）→ 仅用该节点自己的 source_file
- **超大文件**：文件内容截断至 30000 字符 / Round 1
- **LLM 超时**：Round 1 单文件超时 120s，Round 2 超时 180s
- **并发限制**：Round 1 最多 3 个并行 LLM 调用，避免 API 限流

## 不在此范围

- 图谱增量更新（不在本次范围）
- 搜索 UI 改造（前端暂时不变，仅后端查询管道升级）
- 向量化检索 / embedding（本次用图谱社区 + LLM 提取，未来可选加 RAG）
- Round 1 结果缓存（后续迭代）
