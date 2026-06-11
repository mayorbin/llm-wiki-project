# backend/app/services/task_queue.py
"""摄入任务队列——SQLite 持久化 + 内存调度 + 后台 worker。"""
import json
import uuid
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.storage.database import get_db

logger = logging.getLogger(__name__)

# 每项目的内存队列（SQLite 是真实数据源，内存是调度缓存）
_project_queues: dict[str, list] = {}


def create_task(project_id: str, action: str, file_paths: list[str], created_by: str) -> dict:
    """创建新任务——写入 SQLite + 加入内存队列。"""
    db = get_db("tasks")
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""INSERT INTO task_queue (task_id, project_id, action, file_paths, status, created_by, created_at)
        VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
        (task_id, project_id, action, json.dumps(file_paths), created_by, now))
    db.commit()

    task = {"task_id": task_id, "project_id": project_id, "action": action, "status": "queued", "progress": 0}
    if project_id not in _project_queues:
        _project_queues[project_id] = []
    _project_queues[project_id].append(task)

    logger.info("任务已创建", extra={"task_id": task_id, "action": action, "project_id": project_id})
    return task


def get_task_status(task_id: str) -> Optional[dict]:
    """查询任务状态——优先查内存，回退 SQLite。"""
    for queue in _project_queues.values():
        for task in queue:
            if task["task_id"] == task_id:
                return dict(task)
    db = get_db("tasks")
    row = db.execute("SELECT * FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def update_task_status(task_id: str, status: str, progress: int = 0, error_code: str = None, error_message: str = None):
    """更新任务状态——先写 SQLite，再更新内存。"""
    db = get_db("tasks")
    now = datetime.now(timezone.utc).isoformat()
    if status == "running":
        db.execute("UPDATE task_queue SET status=?, progress=?, started_at=? WHERE task_id=?",
            (status, progress, now, task_id))
    elif status in ("completed", "failed"):
        db.execute("UPDATE task_queue SET status=?, progress=?, error_code=?, error_message=?, completed_at=? WHERE task_id=?",
            (status, progress, error_code, error_message, now, task_id))
    else:
        db.execute("UPDATE task_queue SET status=?, progress=? WHERE task_id=?",
            (status, progress, task_id))
    db.commit()
    for queue in _project_queues.values():
        for task in queue:
            if task["task_id"] == task_id:
                task["status"] = status
                task["progress"] = progress


def get_next_queued(project_id: str) -> Optional[dict]:
    """获取项目队列中下一个待执行任务。"""
    if project_id not in _project_queues or not _project_queues[project_id]:
        return None
    for task in _project_queues[project_id]:
        if task["status"] == "queued":
            return task
    return None


async def recover_tasks_on_startup():
    """服务重启时恢复未完成任务。"""
    db = get_db("tasks")
    rows = db.execute("SELECT * FROM task_queue WHERE status IN ('queued', 'running') ORDER BY created_at").fetchall()
    for row in rows:
        task = dict(row)
        if task["status"] == "running":
            db.execute("UPDATE task_queue SET status='queued', progress=0, started_at=NULL WHERE task_id=?", (task["task_id"],))
            task["status"] = "queued"
            task["progress"] = 0
        if task["project_id"] not in _project_queues:
            _project_queues[task["project_id"]] = []
        _project_queues[task["project_id"]].append(task)
    db.commit()
    if rows:
        logger.info(f"启动恢复: {len(rows)} 个未完成任务已重新排队")


def cleanup_expired(max_age_days: int = 7):
    """清理过期的已完成/失败任务。"""
    from datetime import timedelta
    db = get_db("tasks")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    db.execute("DELETE FROM task_queue WHERE status IN ('completed','failed') AND completed_at < ?", (cutoff,))
    db.commit()


# ── 后台任务 Worker ──

async def start_task_worker(poll_interval: float = 5.0):
    """
    后台任务轮询器——在 FastAPI lifespan 中启动。

    每 poll_interval 秒扫描 task_queue 表，将 queued 状态的任务
    取出并执行摄入/图谱构建操作。

    当前实现为同步轮询（简单可靠）。未来可替换为 Celery/Redis 异步队列。
    """
    import asyncio

    logger.info("后台任务 worker 已启动", extra={"poll_interval": poll_interval})

    while True:
        try:
            db = get_db("tasks")
            # 查找所有 queued 状态的任务
            rows = db.execute(
                "SELECT * FROM task_queue WHERE status = 'queued' "
                "ORDER BY created_at ASC LIMIT 10"
            ).fetchall()

            for row in rows:
                task = dict(row)
                task_id = task["task_id"]
                project_id = task["project_id"]
                action = task["action"]
                file_paths = json.loads(task.get("file_paths", "[]"))

                # 尝试获取项目写锁（非阻塞），锁被占用则跳过
                from app.services.lock_manager import LockManager
                from app.config import get_settings
                settings = get_settings()
                lock_mgr = LockManager(Path(settings.data_dir))

                try:
                    lock = lock_mgr.acquire_project_write(project_id, timeout=0.1)
                except Exception:
                    continue  # 锁被占用，下轮再试

                try:
                    update_task_status(task_id, "running", progress=10)
                    logger.info("后台 worker 开始执行任务",
                        extra={"task_id": task_id, "action": action})

                    # 在线程池中执行以避免阻塞 uvicorn 事件循环
                    if action == "ingest":
                        await asyncio.to_thread(_execute_ingest, task_id, project_id, file_paths)
                    elif action == "graph_build":
                        await asyncio.to_thread(_execute_graph_build, task_id, project_id)

                    update_task_status(task_id, "completed", progress=100)
                    logger.info("后台 worker 任务完成", extra={"task_id": task_id})
                except Exception as e:
                    update_task_status(task_id, "failed", progress=0,
                        error_code="WORKER_ERROR",
                        error_message=str(e)[:500])
                    logger.error("后台 worker 任务失败",
                        extra={"task_id": task_id, "error": str(e)})
                finally:
                    lock_mgr.release(lock)

        except Exception as e:
            logger.error("后台 worker 循环异常", extra={"error": str(e)})

        await asyncio.sleep(poll_interval)


def _ingest_single_file(fp: str, base_dir: Path, task_id: str, project_id: str) -> str:
    """处理单个文件的摄入，返回文件路径供后续图谱重建。"""
    from app.storage.file_storage import safe_subdir
    from app.engines.llm_engine import call_llm_with_retry

    raw_path = safe_subdir(base_dir / "raw", fp)
    if not raw_path.exists():
        raise FileNotFoundError(f"源文件不存在: {fp}")

    # 读取文件内容——非 Markdown 文件先转换为文本
    if raw_path.suffix == ".md":
        content_str = raw_path.read_text(encoding="utf-8")
    else:
        try:
            from app.engines.convert_engine import ConvertEngine
            engine = ConvertEngine()
            content_str = engine.convert(raw_path)
        except Exception as e:
            logger.warning("文件转换失败，回退到原始读取", extra={"file": fp, "error": str(e)})
            content = raw_path.read_bytes()[:100*1024]
            content_str = content.decode("utf-8", errors="replace")

    # 调用 LLM 提取知识
    wiki_dir = base_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    index_content = (wiki_dir / "index.md").read_text(encoding="utf-8") if (wiki_dir / "index.md").exists() else ""

    prompt = f"""处理以下源文件并提取关键知识构建 Wiki 页面。

文件路径: {fp}
文件内容:
{content_str[:30000]}

当前 Wiki 索引:
{index_content[:2000]}

请以 JSON 格式返回，提取所有关键数据和表格信息:
{{
  "title": "标题",
  "summary": "3-5句摘要，涵盖核心论点、关键数据",
  "key_claims": ["关键观点1", "关键观点2"],
  "key_data": [{{"label":"数据名称","value":"具体数值或内容"}}],
  "tables": [{{"title":"表格标题","rows":[["列1","列2"],["值1","值2"]]}}],
  "entities": [{{"name":"实体名","type":"person/organization/project"}}],
  "concepts": [{{"name":"概念名","description":"简述"}}]
}}"""

    result = call_llm_with_retry(prompt=prompt, task_id=task_id, project_id=project_id, max_tokens=4096)

    # 写入 wiki 页面
    import json as _json
    try:
        result = result.strip()
        if result.startswith("```"):
            result = result[result.index("\n"):].strip()
        if result.endswith("```"):
            result = result[:-3].strip()
        data = _json.loads(result)
    except _json.JSONDecodeError:
        data = {"title": fp, "summary": result[:500], "key_claims": [], "entities": [], "concepts": []}

    from app.engines.wiki_engine import write_page, update_index, append_log
    from datetime import datetime as _dt, timezone as _tz
    import re as _re

    slug = _re.sub(r'[^a-zA-Z0-9一-鿿_-]', '-', data.get("title", fp)).lower()[:50]
    now = _dt.now(_tz.utc).isoformat()

    page_content = f"""---
title: "{data.get('title', fp)}"
type: source
tags: []
date: {now[:10]}
source_file: {fp}
---

## 摘要
{data.get('summary', '')}

## 关键数据
{chr(10).join(f'- **{d.get("label", "")}**: {d.get("value", "")}' for d in data.get('key_data', []))}

## 表格
{chr(10).join(f'### {t.get("title", "表格")}{chr(10)}' + chr(10).join('| ' + ' | '.join(r) + ' |' for r in t.get('rows', [])) for t in data.get('tables', []))}

## 关键观点
{chr(10).join('- ' + c for c in data.get('key_claims', []))}

## 实体
{chr(10).join(f'- [[{e["name"]}]]' for e in data.get('entities', []))}

## 概念
{chr(10).join(f'- [[{c["name"]}]]: {c.get("description", "")}' for c in data.get('concepts', []))}
"""
    write_page(wiki_dir / "sources" / f"{slug}.md", page_content)
    update_index(wiki_dir, f"- [{data.get('title', fp)}](sources/{slug}.md) — {data.get('summary', '')[:60]}")
    append_log(wiki_dir, f"## [{now[:10]}] ingest | {data.get('title', fp)}")

    # 创建实体和概念页面（使 wikilinks 可解析产生图谱边）
    for ent in data.get('entities', []):
        ent_slug = _re.sub(r'[^a-zA-Z0-9一-鿿_-]', '-', ent.get('name', '')).lower()[:50]
        ent_path = wiki_dir / "entities" / f"{ent_slug}.md"
        if not ent_path.exists():
            ent_content = f"""---
title: "{ent.get('name', '')}"
type: {ent.get('type', 'unknown')}
tags: []
date: {now[:10]}
---
# {ent.get('name', '')}
{ent.get('description', '')[:200]}
"""
            write_page(ent_path, ent_content)
    for cpt in data.get('concepts', []):
        cpt_slug = _re.sub(r'[^a-zA-Z0-9一-鿿_-]', '-', cpt.get('name', '')).lower()[:50]
        cpt_path = wiki_dir / "concepts" / f"{cpt_slug}.md"
        if not cpt_path.exists():
            cpt_content = f"""---
title: "{cpt.get('name', '')}"
type: concept
tags: []
date: {now[:10]}
---
# {cpt.get('name', '')}
{cpt.get('description', '')[:200]}
"""
            write_page(cpt_path, cpt_content)

    return fp


def _execute_ingest(task_id: str, project_id: str, file_paths: list[str]):
    """执行单个摄入任务——多文件并行处理。"""
    from app.config import get_settings

    settings = get_settings()
    base_dir = Path(settings.data_dir) / "projects" / project_id
    total = len(file_paths)
    done = 0

    # 在线程池中并行处理文件（最多 3 个并发 LLM 调用）
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_ingest_single_file, fp, base_dir, task_id, project_id): fp
            for fp in file_paths
        }
        for future in as_completed(futures):
            fp = futures[future]
            try:
                future.result()
                done += 1
                progress = int(30 + (done / total) * 50)  # 30%-80%
                update_task_status(task_id, "running", progress=progress)
                logger.info("文件摄入完成", extra={"task_id": task_id, "file": fp, "done": done, "total": total})
            except Exception as e:
                logger.error("文件摄入失败", extra={"task_id": task_id, "file": fp, "error": str(e)})

    if done == 0:
        raise RuntimeError(f"所有 {total} 个文件摄入均失败")

    update_task_status(task_id, "running", progress=85)

    # 检查是否启用自动重建图谱
    import json as _json
    from app.storage.database import get_db as _get_db
    should_rebuild = True
    try:
        db = _get_db("users")
        row = db.execute(
            "SELECT settings FROM project_settings WHERE project_id = ?", (project_id,),
        ).fetchone()
        if row:
            s = _json.loads(row["settings"])
            should_rebuild = s.get("features", {}).get("auto_graph_rebuild", True)
    except Exception:
        pass

    if should_rebuild:
        from app.engines.graph_engine import GraphEngine
        wiki_dir = base_dir / "wiki"
        graph_dir = base_dir / "graph"
        engine = GraphEngine(wiki_dir=wiki_dir, graph_dir=graph_dir)
        engine.build(run_inference=True)

    update_task_status(task_id, "running", progress=100)


def _execute_graph_build(task_id: str, project_id: str):
    """执行图谱构建任务。"""
    from app.config import get_settings
    from app.engines.graph_engine import GraphEngine

    settings = get_settings()
    base_dir = Path(settings.data_dir) / "projects" / project_id
    wiki_dir = base_dir / "wiki"
    graph_dir = base_dir / "graph"

    update_task_status(task_id, "running", progress=50)
    engine = GraphEngine(wiki_dir=wiki_dir, graph_dir=graph_dir)
    engine.build(run_inference=False)
    update_task_status(task_id, "running", progress=100)

