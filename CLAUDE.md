# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a workspace repository for **LLM Wiki Agent** — a coding-agent skill that maintains a persistent, interlinked knowledge wiki. Source documents are dropped into `raw/`, and the agent (Claude Code or equivalent) ingests them, extracts knowledge, builds entity/concept pages, cross-references everything with `[[wikilinks]]`, and generates an interactive vis.js knowledge graph.

The actual project lives in `llm-wiki-agent/`. All commands below assume you're running from that directory.

## Architecture

```
llm-wiki-agent/
├── CLAUDE.md              # Agent schema: page formats, workflows, naming conventions
├── AGENTS.md / GEMINI.md  # Same schema adapted for Codex/Gemini CLI
├── .claude/commands/      # Claude Code slash commands (wiki-ingest, wiki-query, wiki-lint, wiki-graph)
├── tools/                 # Standalone Python scripts
│   ├── ingest.py          # Ingest sources → wiki pages (core operation)
│   ├── query.py           # Query the wiki with LLM synthesis
│   ├── health.py          # Deterministic structural checks (no LLM, run every session)
│   ├── lint.py            # Semantic quality checks + graph-aware analysis (uses LLM)
│   ├── build_graph.py     # Knowledge graph: wikilink extraction + LLM-inferred edges + Louvain community detection
│   ├── heal.py            # Auto-generate missing entity pages
│   ├── refresh.py         # Re-ingest sources when raw documents change
│   ├── pdf2md.py          # Convert PDF/arXiv to markdown (arxiv2md/marker/pymupdf4llm backends)
│   └── file_to_md.py      # Batch directory conversion via markitdown
├── wiki/                  # The knowledge layer (agent-maintained)
│   ├── index.md           # Catalog of all pages
│   ├── log.md             # Append-only operation log
│   ├── overview.md        # Living synthesis across all sources
│   ├── sources/           # One summary page per ingested document
│   ├── entities/          # Auto-created pages for people, companies, projects
│   ├── concepts/          # Auto-created pages for ideas, frameworks, methods
│   └── syntheses/         # Saved query answers
├── graph/                 # Auto-generated: graph.json + graph.html (vis.js)
└── raw/                   # Immutable source documents
```

**Core design**: The agent (not the user) writes wiki pages. The user only drops source documents into `raw/` and asks questions. All wiki content is plain markdown with YAML frontmatter and `[[wikilinks]]`.

**Graph pipeline** (two-pass):
1. Deterministic: parse all `[[wikilinks]]` → `EXTRACTED` edges
2. Semantic: LLM infers implicit relationships → `INFERRED` (confidence ≥0.7) or `AMBIGUOUS` edges
3. Louvain community detection clusters related topics
4. SHA256 caching skips unchanged pages on rebuild

## Common Commands

```bash
# All commands run from llm-wiki-agent/

# Ingest a source document (auto-converts PDF, DOCX, etc. via markitdown)
python tools/ingest.py raw/my-source.md

# Query the wiki
python tools/query.py "What are the main themes?"

# Health check (deterministic, no LLM cost — run every session)
python tools/health.py

# Lint (semantic + graph-aware — run every 10-15 ingests)
python tools/lint.py

# Build knowledge graph
python tools/build_graph.py --open                    # full build + open in browser
python tools/build_graph.py --no-infer --report       # wikilinks only + health report

# Convert arXiv paper to markdown before ingesting
python tools/pdf2md.py 2401.12345

# Batch convert a directory
python tools/file_to_md.py --input_dir raw/imports/

# Auto-heal missing entity pages
python tools/heal.py
```

## Dependencies

- **Runtime**: `litellm~=1.83.10`, `networkx~=3.6.1`, `markitdown[all]>=0.1.5`, `tqdm>=4.67.3`
- **Install**: `pip install -r llm-wiki-agent/requirements.txt`
- **Optional backends for PDF conversion**: `arxiv2markdown`, `marker-pdf`, `pymupdf4llm`
- **LLM API key**: Set `ANTHROPIC_API_KEY` (or provider-specific key). Override model via `LLM_MODEL` env var.

## Key Conventions

- Wiki pages use `[[PageName]]` wikilinks for cross-references
- Source slugs are `kebab-case`; entity/concept pages use `TitleCase.md`
- Log format: `## [YYYY-MM-DD] <operation> | <title>` — grep-parseable
- Non-markdown files are auto-converted at ingest time (supported: PDF, DOCX, PPTX, XLSX, HTML, EPUB, IPYNB, CSV, JSON, XML, and more)
- Health runs before lint — linting empty/stub files wastes tokens
