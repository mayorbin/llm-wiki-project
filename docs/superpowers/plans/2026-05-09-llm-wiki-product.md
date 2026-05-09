# LLM Wiki 产品实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于设计规格文档，从零构建一个完整的 LLM Wiki 知识库产品，包含 Python FastAPI 后端和 Vue3 前端。

**Architecture:** 前后端分离——FastAPI 三层架构（API→Service→Engine）+ Vue3 SPA（Pinia + AntV G6 + markdown-it）。文件系统存储 Wiki，SQLite 管理用户/项目/审计日志。所有 LLM 调用通过 litellm 统一入口，支持多 Provider。

**Tech Stack:** Python 3.10+ / FastAPI / litellm / NetworkX / markitdown / SQLite / Vue3 / Vite / Pinia / AntV G6 v5 / markdown-it + DOMPurify

**代码要求:** 所有 Python/TypeScript 代码使用中文注释，每个模块有完整的单元测试。

---

## Phase 1: 后端基础架构

### Task 1: 项目脚手架与配置管理

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/config.example.yaml`
- Create: `backend/.env.example`
- Test: `backend/tests/unit/test_config.py`

- [ ] **Step 1: 创建项目目录结构和 pyproject.toml**

```bash
mkdir -p backend/app/{api,services,engines,models,storage,utils}
mkdir -p backend/tests/{unit,integration}
mkdir -p backend/alembic/versions
```

```toml
# backend/pyproject.toml
[project]
name = "llm-wiki"
version = "0.1.0"
description = "LLM Wiki 知识库产品后端"
requires-python = ">=3.10,<3.15"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.30,<1.0",
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "litellm>=1.50,<2.0",
    "networkx>=3.0,<4.0",
    "markitdown[all]>=0.1.5,<1.0",
    "python-jose[cryptography]>=3.3,<4.0",
    "passlib[bcrypt]>=1.7,<2.0",
    "filelock>=3.13,<4.0",
    "python-multipart>=0.0.9,<1.0",
    "pyyaml>=6.0,<7.0",
    "alembic>=1.13,<2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-asyncio>=0.23,<1.0",
    "httpx>=0.27,<1.0",
    "ruff>=0.4,<1.0",
]
```

- [ ] **Step 2: 编写配置管理模块**

```python
# backend/app/config.py
"""
配置管理模块。

配置加载优先级（高→低）：
1. 环境变量 LLM_WIKI_*
2. .env 文件
3. config.yaml
4. 代码默认值
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局应用配置，所有字段可通过环境变量 LLM_WIKI_<FIELD> 覆盖。"""

    # ── 应用基础 ──
    app_name: str = "LLM Wiki"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR

    # ── 数据目录 ──
    data_dir: str = "./data"

    # ── 默认 LLM 配置（全局默认，项目可覆盖） ──
    llm_provider: str = "openai_compatible"  # deepseek | glm | openai_compatible
    llm_model: str = "deepseek/deepseek-v4-flash"  # litellm model id
    llm_api_base: str = "http://localhost:8000/v1"  # OpenAI 兼容 API 地址
    llm_api_key: str = ""  # 必填，无默认值，启动时校验
    llm_temperature: float = 0.3  # 0.0–2.0，知识提取需要确定性
    llm_max_tokens: int = 8192
    llm_timeout: int = 120  # 秒
    llm_max_retries: int = 3
    llm_extra_headers: dict = {}  # 自定义 HTTP 头
    llm_fast_model: str = ""  # 轻量任务模型，空则复用 llm_model

    # ── 服务 ──
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 2  # Gunicorn workers
    secret_key: str = ""  # JWT 签名密钥，必填，启动时校验

    # ── 安全 ──
    max_upload_size_mb: int = 100
    cors_origins: list[str] = ["*"]
    registration_open: bool = False

    # ── 保留策略 ──
    snapshot_retention_days: int = 30
    task_history_days: int = 7
    log_retention_days: int = 90

    # ── JWT ──
    access_token_expire_hours: int = 24
    refresh_token_expire_days: int = 7

    model_config = {
        "env_prefix": "LLM_WIKI_",
        "env_file": ".env",
        "extra": "ignore",
    }

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "Settings":
        """从 YAML 配置文件加载设置，优先级低于环境变量。"""
        import yaml

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        # 展平嵌套结构为点分隔键
        flat: dict[str, str] = {}
        if yaml_data and isinstance(yaml_data, dict):
            llm = yaml_data.get("llm", {})
            if isinstance(llm, dict):
                for k, v in llm.items():
                    flat[f"llm_{k}"] = str(v)
            svc = yaml_data.get("service", {})
            if isinstance(svc, dict):
                for k, v in svc.items():
                    flat[k] = str(v)
            sec = yaml_data.get("security", {})
            if isinstance(sec, dict):
                for k, v in sec.items():
                    flat[k] = str(v)
            ret = yaml_data.get("retention", {})
            if isinstance(ret, dict):
                for k, v in ret.items():
                    flat[k] = str(v)
            # 顶层简单字段
            for k in ("app_name", "debug", "log_level", "data_dir"):
                if k in yaml_data:
                    flat[k] = str(yaml_data[k])

        return cls(**flat)

    def validate_required(self):
        """启动时校验必填项。"""
        errors = []
        if not self.llm_api_key:
            errors.append("LLM_WIKI_LLM_API_KEY 未设置")
        if not self.secret_key:
            errors.append("LLM_WIKI_SECRET_KEY 未设置")
        if errors:
            raise ConfigurationError("; ".join(errors))


class ConfigurationError(Exception):
    """配置错误异常。"""
    pass


# 全局单例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        # 尝试从 config.yaml 加载
        yaml_path = Path("config.yaml")
        if yaml_path.exists():
            _settings = Settings.from_yaml(yaml_path)
    return _settings
```

- [ ] **Step 3: 编写配置测试**

```python
# backend/tests/unit/test_config.py
"""
配置管理模块的单元测试。
"""

import os
import pytest
from pathlib import Path
from app.config import Settings, ConfigurationError


class TestSettings:
    """测试 Settings 配置加载。"""

    def test_默认值(self):
        """未设置任何外部配置时，使用代码默认值。"""
        settings = Settings()
        assert settings.app_name == "LLM Wiki"
        assert settings.port == 8000
        assert settings.access_token_expire_hours == 24
        assert settings.log_level == "INFO"

    def test_环境变量覆盖(self, monkeypatch):
        """环境变量应覆盖默认值。"""
        monkeypatch.setenv("LLM_WIKI_PORT", "9999")
        monkeypatch.setenv("LLM_WIKI_LLM_MODEL", "glm/glm-47")
        settings = Settings()
        assert settings.port == 9999
        assert settings.llm_model == "glm/glm-47"

    def test_必填项校验失败_缺少secret_key(self):
        """缺少 secret_key 时校验应失败。"""
        settings = Settings(llm_api_key="sk-test")
        with pytest.raises(ConfigurationError, match="SECRET_KEY"):
            settings.validate_required()

    def test_必填项校验成功(self):
        """所有必填项齐全时校验通过。"""
        settings = Settings(llm_api_key="sk-test", secret_key="super-secret-32")
        settings.validate_required()  # 不应抛异常

    def test_cors_origins默认值(self):
        """CORS 默认允许所有来源。"""
        settings = Settings()
        assert settings.cors_origins == ["*"]

    def test_from_yaml_加载(self, tmp_path):
        """从 YAML 文件加载配置。"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("""
llm:
  model: custom/model
  temperature: 0.5
service:
  port: 8080
        """)
        settings = Settings.from_yaml(yaml_path)
        assert settings.llm_model == "custom/model"
        assert settings.llm_temperature == 0.5
        assert settings.port == 8080
```

- [ ] **Step 4: 运行测试确认失败（项目尚未安装依赖）**

```bash
cd backend && pip install -e ".[dev]" && python -m pytest tests/unit/test_config.py -v
```

- [ ] **Step 5: 编写 FastAPI 入口和启动逻辑**

```python
# backend/app/main.py
"""
FastAPI 应用入口。

启动时执行：
1. 加载配置
2. 初始化日志系统
3. 初始化数据库连接
4. 恢复未完成的任务
5. 注册路由和中间件
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import setup_logging
from app.api import auth, projects, files, ingestion, knowledge, graph, maintenance, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化，关闭时清理。"""
    settings = get_settings()
    settings.validate_required()

    # 初始化日志
    setup_logging(
        log_dir=Path(settings.data_dir) / "logs",
        level=settings.log_level,
    )

    # 初始化数据库
    from app.storage.database import init_db
    init_db(settings.data_dir)

    # 恢复未完成的任务
    from app.services.task_queue import recover_tasks_on_startup
    await recover_tasks_on_startup()

    yield  # 应用运行中

    # 关闭时清理（预留）


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(projects.router, prefix="/api", tags=["项目"])
app.include_router(files.router, prefix="/api", tags=["文件"])
app.include_router(ingestion.router, prefix="/api", tags=["摄入"])
app.include_router(knowledge.router, prefix="/api", tags=["知识"])
app.include_router(graph.router, prefix="/api", tags=["图谱"])
app.include_router(maintenance.router, prefix="/api", tags=["维护"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理"])


@app.get("/api/ping")
async def ping():
    """存活探针——零依赖，仅验证进程存活。"""
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/health")
async def health(deep: bool = False):
    """就绪探针——验证进程 + 关键依赖可用。"""
    checks = {"database": "ok"}
    # 检查文件系统可写
    try:
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".health_check"
        test_file.touch()
        test_file.unlink()
        checks["file_system"] = "ok"
    except Exception:
        checks["file_system"] = "error"

    # 深度检查：LLM 连通性
    if deep:
        from app.engines.llm_engine import verify_llm_connection
        checks["llm_api"] = "ok" if verify_llm_connection(settings) else "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "version": settings.app_version,
        "checks": checks,
    }
```

- [ ] **Step 6: 编写 config.example.yaml 和 .env.example**

```yaml
# backend/config.example.yaml
app_name: "LLM Wiki"
debug: false
log_level: "INFO"
data_dir: "./data"

llm:
  provider: "openai_compatible"
  model: "deepseek/deepseek-v4-flash"
  api_base: "http://localhost:8000/v1"
  api_key: "${LLM_WIKI_LLM_API_KEY}"
  temperature: 0.3
  max_tokens: 8192
  extra_headers: {}

service:
  host: "0.0.0.0"
  port: 8000
  workers: 4
  secret_key: "${LLM_WIKI_SECRET_KEY}"

security:
  max_upload_size_mb: 100
  cors_origins:
    - "http://localhost:5173"
  registration_open: false

retention:
  snapshot_days: 30
  task_history_days: 7
  log_days: 90
```

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: 后端项目脚手架——配置管理、FastAPI入口、健康检查"
```

---

### Task 2: 日志系统

**Files:**
- Create: `backend/app/logging_config.py`
- Test: `backend/tests/unit/test_logging.py`

- [ ] **Step 1: 编写结构化日志模块**

```python
# backend/app/logging_config.py
"""
应用日志系统——结构化 JSON Lines 输出。

日志级别约定：
  DEBUG   — 开发调试细节（SQL 查询、LLM prompt 全文）
  INFO    — 正常业务流程（摄入开始/完成、API 响应码）
  WARNING — 可恢复的异常（LLM 重试、锁等待超时）
  ERROR   — 需要关注的错误（摄入失败、磁盘写入失败）
  CRITICAL— 服务级故障（数据库损坏、所有 LLM 后端不可用）
"""

import json
import logging
import sys
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler


class StructuredFormatter(logging.Formatter):
    """JSON Lines 结构化日志格式化器，方便 grep / jq / 日志聚合工具解析。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%(msecs)03d"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": f"{record.module}:{record.funcName}:{record.lineno}",
        }

        # 附加上下文字段
        for key in ("project_id", "user_id", "task_id", "request_id", "duration_ms"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # 异常信息（仅在 ERROR 级别记录完整堆栈）
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
            if record.exc_text:
                log_entry["error"]["traceback"] = record.exc_text.split("\n")

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(log_dir: Path, level: str = "INFO"):
    """
    初始化日志系统。

    handler:
      - app.log: 结构化 JSON，50MB 轮转 × 10
      - error.log: 仅 ERROR+，20MB 轮转 × 5
      - stdout: 彩色可读格式（DEBUG 模式启用）
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    # 清除已有的 handler（防止重复添加）
    root.handlers.clear()

    # Handler 1: 全量日志 → app.log
    app_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(StructuredFormatter())
    root.addHandler(app_handler)

    # Handler 2: 错误日志 → error.log
    err_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(StructuredFormatter())
    root.addHandler(err_handler)

    # Handler 3: 控制台（仅 DEBUG 模式）
    if level.upper() == "DEBUG":
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s"
        ))
        root.addHandler(console)

    # 降低第三方库日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取带模块名的 logger。"""
    return logging.getLogger(name)
```

- [ ] **Step 2: 编写日志测试**

```python
# backend/tests/unit/test_logging.py
"""日志系统测试。"""

import json
import logging
import pytest
from pathlib import Path
from app.logging_config import setup_logging, StructuredFormatter


class TestStructuredFormatter:
    """结构化格式化器测试。"""

    def test_基础日志格式(self):
        """普通 INFO 日志应输出有效 JSON Lines。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="测试消息", args=(), exc_info=None,
        )
        record.duration_ms = 150
        result = formatter.format(record)
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["msg"] == "测试消息"
        assert data["duration_ms"] == 150
        assert "error" not in data

    def test_异常日志包含堆栈(self):
        """ERROR 日志应包含异常类型和 traceback。"""
        formatter = StructuredFormatter()
        try:
            raise ValueError("测试异常")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="test.py",
                lineno=1, msg="出错了", args=(), exc_info=sys.exc_info(),
            )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["level"] == "ERROR"
        assert data["error"]["type"] == "ValueError"
        assert data["error"]["message"] == "测试异常"
        assert "traceback" in data["error"]

    def test_上下文字段注入(self):
        """通过 record 属性注入上下文字段。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="任务开始", args=(), exc_info=None,
        )
        record.task_id = "t-123"
        record.project_id = "p-456"
        result = formatter.format(record)
        data = json.loads(result)
        assert data["task_id"] == "t-123"
        assert data["project_id"] == "p-456"


class TestSetupLogging:
    """日志初始化测试。"""

    def test_创建日志目录和文件(self, tmp_path):
        """初始化后应创建日志文件。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        assert (log_dir / "app.log").exists()
        assert (log_dir / "error.log").exists()

    def test_不重复添加handler(self, tmp_path):
        """多次调用 setup_logging 不应导致 handler 重复。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        root = logging.getLogger()
        handler_count_before = len(root.handlers)
        setup_logging(log_dir, level="INFO")
        assert len(root.handlers) == handler_count_before

    def test_DEBUG模式启用控制台(self, tmp_path):
        """DEBUG 级别应额外添加 stdout handler。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        root_before = len(logging.getLogger().handlers)
        setup_logging(log_dir, level="DEBUG")
        root_after = len(logging.getLogger().handlers)
        assert root_after > root_before
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && python -m pytest tests/unit/test_logging.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/logging_config.py backend/tests/unit/test_logging.py
git commit -m "feat: 结构化日志系统——JSON Lines输出/三级handler/上下文注入"
```

---

### Task 3: 数据库初始化与 Schema

**Files:**
- Create: `backend/app/storage/__init__.py`
- Create: `backend/app/storage/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial.py`
- Test: `backend/tests/unit/test_database.py`

- [ ] **Step 1: 编写数据库模块**

```python
# backend/app/storage/database.py
"""
SQLite 数据库管理模块。

数据库文件：
  - data/users.db   —— 用户、项目、项目成员、项目设置
  - data/tasks.db   —— 摄入任务队列
  - data/audit.db   —— 审计日志

所有数据库连接在应用生命周期内复用，使用 WAL 模式提升并发读取性能。
"""

import sqlite3
from pathlib import Path
from app.config import get_settings

# 数据库连接缓存
_connections: dict[str, sqlite3.Connection] = {}


def get_db(db_name: str = "users") -> sqlite3.Connection:
    """获取指定数据库的连接（自动创建并启用 WAL 模式）。"""
    global _connections
    if db_name in _connections:
        return _connections[db_name]

    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / f"{db_name}.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 提升并发读取性能
    conn.execute("PRAGMA foreign_keys=ON")
    _connections[db_name] = conn
    return conn


def init_db(data_dir: str):
    """
    首次启动时初始化所有数据库表。

    使用 IF NOT EXISTS 确保幂等（多次调用不重复创建）。
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    # 用户数据库
    users_db = get_db("users")
    users_db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            deleted_at TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            archived_at TEXT
        );

        CREATE TABLE IF NOT EXISTS project_members (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'editor',
            joined_at TEXT NOT NULL,
            PRIMARY KEY (project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS project_settings (
            project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            settings TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );
    """)

    # 任务数据库
    tasks_db = get_db("tasks")
    tasks_db.executescript("""
        CREATE TABLE IF NOT EXISTS task_queue (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            action TEXT NOT NULL,
            file_paths TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            error_message TEXT,
            error_detail TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            snapshot_dir TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_task_project
            ON task_queue(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_task_created
            ON task_queue(created_at);
    """)

    # 审计数据库
    audit_db = get_db("audit")
    audit_db.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            target TEXT NOT NULL,
            detail TEXT,
            result TEXT NOT NULL,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_project_time
            ON audit_log(project_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
    """)

    # 提交所有建表语句
    for conn in _connections.values():
        conn.commit()


def close_all_db():
    """关闭所有数据库连接（测试清理用）。"""
    global _connections
    for conn in _connections.values():
        conn.close()
    _connections.clear()
```

- [ ] **Step 2: 编写数据库测试**

```python
# backend/tests/unit/test_database.py
"""数据库初始化测试。"""

import sqlite3
import pytest
from app.storage.database import init_db, get_db, close_all_db


@pytest.fixture(autouse=True)
def cleanup_db(monkeypatch, tmp_path):
    """每个测试使用独立的数据目录，测试后清理连接。"""
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    close_all_db()  # 确保无旧连接
    yield
    close_all_db()


class TestInitDB:
    """数据库初始化测试。"""

    def test_users表创建(self, monkeypatch, tmp_path):
        """users.db 应包含 users/projects/project_members/project_settings 表。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        conn = get_db("users")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "users" in table_names
        assert "projects" in table_names
        assert "project_members" in table_names
        assert "project_settings" in table_names

    def test_tasks表创建(self, monkeypatch, tmp_path):
        """tasks.db 应包含 task_queue 表。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        conn = get_db("tasks")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any(r["name"] == "task_queue" for r in tables)

    def test_audit表创建(self, monkeypatch, tmp_path):
        """audit.db 应包含 audit_log 表。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        conn = get_db("audit")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any(r["name"] == "audit_log" for r in tables)

    def test_幂等初始化(self, monkeypatch, tmp_path):
        """多次调用 init_db 不报错。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        init_db(str(tmp_path))  # 不应抛异常

    def test_WAL模式(self, monkeypatch, tmp_path):
        """数据库应启用 WAL 模式。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        conn = get_db("users")
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_外键约束启用(self, monkeypatch, tmp_path):
        """外键约束应启用。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        init_db(str(tmp_path))
        conn = get_db("users")
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1
```

- [ ] **Step 3: 配置 Alembic**

```ini
# backend/alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite:///data/users.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# backend/alembic/env.py
"""Alembic 迁移环境配置。

SQLite 仅支持 RENAME TABLE 和 ADD COLUMN，render_as_batch=True 让 Alembic
对不兼容的 ALTER 操作使用 "创建新表 → 复制 → 删旧表 → 重命名" 的批量重建策略。
"""

from alembic import context

# SQLite 批量迁移模式
context.configure(
    connection=connection,
    target_metadata=None,
    render_as_batch=True,
)

with context.begin_transaction():
    context.run_migrations()
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && python -m pytest tests/unit/test_database.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/ backend/alembic/ backend/alembic.ini backend/tests/unit/test_database.py
git commit -m "feat: SQLite 数据库初始化——三库四表、WAL模式、Alembic迁移"
```

---

---

## Phase 2: 后端核心引擎

### Task 4: 用户模型与认证服务

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/deps.py`
- Test: `backend/tests/unit/test_auth_service.py`

**模式说明**（后续 CRUD 类 Task 的参考模板）：

所有 Service 层遵循统一模式：接收数据库连接和配置 → 执行业务逻辑 → 返回 Pydantic 模型。API 路由层通过 `deps.py` 注入依赖（数据库连接、当前用户）。

- [ ] **Step 1: 编写 Pydantic 数据模型**

```python
# backend/app/models/user.py
"""用户和项目的 Pydantic 数据模型。"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """创建用户请求。"""
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=100)


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: str
    username: str
    display_name: str
    role: str  # admin | user
    is_admin: bool
    is_active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> "UserResponse":
        """从 SQLite 行记录构造。"""
        return cls(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            is_admin=row["role"] == "admin",
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token 响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class RefreshRequest(BaseModel):
    """刷新 Token 请求。"""
    refresh_token: str


class ProjectMemberResponse(BaseModel):
    """项目成员响应。"""
    user_id: str
    username: str
    display_name: str
    role: str  # owner | editor | viewer
    joined_at: str
```

- [ ] **Step 2: 编写认证服务**

```python
# backend/app/services/auth_service.py
"""
认证服务——注册、登录、Token 管理。

JWT 设计：
  - access_token:  24h，负载含 user_id + username + role
  - refresh_token: 7d， 负载含 user_id + type:"refresh"
  - 签名算法 HS256，密钥为 LLM_WIKI_SECRET_KEY

用户注销采用软删除（deleted_at 字段），不物理删除数据。
"""

import uuid
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext  # 密码哈希
from jose import jwt, JWTError  # JWT 签发和验证

from app.config import get_settings
from app.storage.database import get_db

logger = logging.getLogger(__name__)

# bcrypt 密码上下文
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token 黑名单（内存，存 refresh_token 的 jti）
_token_blacklist: set[str] = set()


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, username: str, role: str) -> str:
    """签发短期 access_token（24h）。"""
    settings = get_settings()
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_expire_hours),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    """签发长期 refresh_token（7d），仅用于刷新。"""
    settings = get_settings()
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT，返回负载字典，验证失败返回 None。"""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        return None


def register_user(username: str, password: str, display_name: str = "") -> UserResponse:
    """注册新用户。"""
    db = get_db("users")
    user_id = f"u_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat()

    try:
        db.execute(
            """INSERT INTO users (id, username, password_hash, display_name, role, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, hash_password(password), display_name, "user", now),
        )
        db.commit()
    except Exception as e:
        if "UNIQUE" in str(e):
            raise ValueError(f"用户名 {username} 已存在") from e
        raise

    return UserResponse(
        id=user_id, username=username, display_name=display_name,
        role="user", is_admin=False, is_active=True, created_at=now,
    )


def login(username: str, password: str) -> TokenResponse:
    """验证用户凭据，签发 Token 对。"""
    db = get_db("users")
    row = db.execute(
        "SELECT id, username, password_hash, role, is_active, deleted_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        raise ValueError("用户名或密码错误")

    if not row["is_active"] or row["deleted_at"]:
        raise ValueError("账号已被禁用或注销")

    return TokenResponse(
        access_token=create_access_token(row["id"], row["username"], row["role"]),
        refresh_token=create_refresh_token(row["id"]),
        expires_in=get_settings().access_token_expire_hours * 3600,
    )


def refresh_access_token(refresh_token: str) -> TokenResponse:
    """使用 refresh_token 换取新的 Token 对（滚动刷新）。"""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("无效的 refresh_token")

    if payload["jti"] in _token_blacklist:
        raise ValueError("Token 已被撤销")

    user_id = payload["sub"]
    db = get_db("users")
    row = db.execute(
        "SELECT id, username, role, is_active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not row or not row["is_active"]:
        raise ValueError("用户不存在或已禁用")

    # 旧 refresh_token 加入黑名单（防止重放）
    _token_blacklist.add(payload["jti"])

    return TokenResponse(
        access_token=create_access_token(row["id"], row["username"], row["role"]),
        refresh_token=create_refresh_token(row["id"]),
        expires_in=get_settings().access_token_expire_hours * 3600,
    )


def logout(refresh_token: str):
    """登出——将 refresh_token 加入黑名单。"""
    payload = decode_token(refresh_token)
    if payload:
        _token_blacklist.add(payload["jti"])


def get_user_projects(user_id: str) -> list[dict]:
    """获取用户所属项目列表。"""
    db = get_db("users")
    rows = db.execute(
        """SELECT p.id, p.name, pm.role, p.status
           FROM project_members pm
           JOIN projects p ON p.id = pm.project_id
           WHERE pm.user_id = ?
           ORDER BY p.created_at DESC""",
        (user_id,),
    ).fetchall()

    return [
        {
            "id": r["id"], "name": r["name"],
            "role": r["role"], "status": r["status"]
        }
        for r in rows
    ]
```

- [ ] **Step 3: 编写认证测试（TDD 模式）**

```python
# backend/tests/unit/test_auth_service.py
"""认证服务测试。"""

import pytest
from app.services.auth_service import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, register_user, login, refresh_access_token,
)


class TestPasswordHashing:
    """密码哈希测试。"""

    def test_hash_verify成功(self):
        """哈希后可正确验证。"""
        hashed = hash_password("my-secret")
        assert verify_password("my-secret", hashed)

    def test_wrong密码验证失败(self):
        """错误密码应验证失败。"""
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_same密码不同hash(self):
        """相同明文两次哈希结果应不同（salt）。"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestJWT:
    """JWT token 签发与验证测试。"""

    def test_access_token往返(self, monkeypatch):
        """签发后能正常解码，负载包含正确字段。"""
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        token = create_access_token("u_1", "zhangsan", "user")
        payload = decode_token(token)
        assert payload["sub"] == "u_1"
        assert payload["username"] == "zhangsan"
        assert payload["role"] == "user"
        assert payload["type"] == "access"

    def test_refresh_token类型正确(self, monkeypatch):
        """refresh_token 的 type 字段为 refresh。"""
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        token = create_refresh_token("u_1")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert "username" not in payload  # refresh 不含 username

    def test_invalid_token解码失败(self, monkeypatch):
        """无效 token 解码返回 None。"""
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        assert decode_token("garbage") is None


class TestLogin:
    """登录流程测试。"""

    def test_注册后登录成功(self, monkeypatch, tmp_path):
        """注册新用户 → 登录应返回有效 Token。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        # 初始化数据库
        from app.storage.database import init_db
        init_db(str(tmp_path))
        # 注册
        user = register_user("testuser", "password123", "测试用户")
        assert user.username == "testuser"
        # 登录
        token = login("testuser", "password123")
        assert token.access_token
        assert token.refresh_token

    def test_错误密码登录失败(self, monkeypatch, tmp_path):
        """错误密码应抛出异常。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        from app.storage.database import init_db
        init_db(str(tmp_path))
        register_user("testuser", "password123")
        with pytest.raises(ValueError, match="用户名或密码错误"):
            login("testuser", "wrong")

    def test_Token刷新(self, monkeypatch, tmp_path):
        """refresh_token 应能换取新 Token 对。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        from app.storage.database import init_db
        init_db(str(tmp_path))
        register_user("testuser", "password123")
        original = login("testuser", "password123")
        new_tokens = refresh_access_token(original.refresh_token)
        assert new_tokens.access_token
        assert new_tokens.refresh_token
        assert new_tokens.access_token != original.access_token

    def test_重复使用同一refresh_token应失败(self, monkeypatch, tmp_path):
        """refresh_token 滚动刷新后旧 token 应失效（黑名单）。"""
        monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars")
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        from app.storage.database import init_db
        init_db(str(tmp_path))
        register_user("testuser", "password123")
        original = login("testuser", "password123")
        refresh_access_token(original.refresh_token)  # 第一次刷新成功
        with pytest.raises(ValueError, match="Token 已被撤销"):
            refresh_access_token(original.refresh_token)  # 第二次应失败
```

- [ ] **Step 4: 编写认证 API 路由**

```python
# backend/app/api/auth.py
"""认证 API 路由。"""
from fastapi import APIRouter, HTTPException, Depends
from app.models.user import LoginRequest, RefreshRequest, UserCreate, TokenResponse, UserResponse
from app.services import auth_service
from app.api.deps import get_current_user

router = APIRouter()

@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """用户登录，返回 access_token + refresh_token。"""
    try:
        return auth_service.login(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    """使用 refresh_token 换取新的 Token 对。"""
    try:
        return auth_service.refresh_access_token(req.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/register", response_model=UserResponse)
async def register(req: UserCreate):
    """注册新用户（registration_open=false 则拒绝）。"""
    from app.config import get_settings
    if not get_settings().registration_open:
        raise HTTPException(status_code=403, detail="注册功能已关闭")
    try:
        return auth_service.register_user(req.username, req.password, req.display_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息和项目列表。"""
    projects = auth_service.get_user_projects(user["id"])
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name", ""),
            "role": user["role"],
            "is_admin": user["role"] == "admin",
        },
        "projects": projects,
    }


@router.post("/auth/logout")
async def logout(req: RefreshRequest):
    """登出——撤销 refresh_token。"""
    auth_service.logout(req.refresh_token)
    return {"status": "ok"}
```

- [ ] **Step 5: 编写认证依赖（get_current_user）**

```python
# backend/app/api/deps.py
"""
FastAPI 依赖注入模块。

提供：
  - get_current_user: 从 Authorization header 提取 JWT，返回用户信息
  - get_project_role: 校验用户在项目中的角色，返回 project_id + role
"""

from fastapi import HTTPException, Depends, Header
from app.services.auth_service import decode_token
from app.storage.database import get_db


async def get_current_user(authorization: str = Header(...)) -> dict:
    """从 Bearer Token 提取当前用户信息。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少认证信息")
    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效或过期的 Token")
    return {
        "id": payload["sub"],
        "username": payload["username"],
        "role": payload["role"],
    }


def require_role(*allowed_roles: str):
    """创建角色校验依赖工厂。

    用法: @router.delete("/files/{id}", dependencies=[Depends(require_role("owner", "editor"))])
    """
    async def check(project_id: str, user: dict = Depends(get_current_user)):
        db = get_db("users")
        row = db.execute(
            "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user["id"]),
        ).fetchone()
        if not row or row["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
    return check


def get_project_context(project_id: str, user: dict) -> dict:
    """获取用户在某项目中的上下文（角色 + 项目状态）。"""
    db = get_db("users")
    row = db.execute(
        """SELECT pm.role, p.status
           FROM project_members pm
           JOIN projects p ON p.id = pm.project_id
           WHERE pm.project_id=? AND pm.user_id=?""",
        (project_id, user["id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    return {"project_id": project_id, "role": row["role"], "status": row["status"]}
```

- [ ] **Step 6: 运行测试并 Commit**

```bash
cd backend && python -m pytest tests/unit/test_auth_service.py -v
git add backend/app/models/user.py backend/app/services/auth_service.py backend/app/api/auth.py backend/app/api/deps.py backend/tests/unit/test_auth_service.py
git commit -m "feat: 认证系统——JWT签发/刷新/黑名单、bcrypt密码、角色依赖注入"
```

---

### Task 5: LLM 引擎（多 Provider）

**Files:**
- Create: `backend/app/engines/__init__.py`
- Create: `backend/app/engines/llm_engine.py`
- Test: `backend/tests/unit/test_llm_engine.py`

- [ ] **Step 1: 编写 LLM 引擎**

```python
# backend/app/engines/llm_engine.py
"""
LLM 调用引擎——基于 litellm 的统一入口。

支持所有 OpenAI 兼容协议的模型：
  - DeepSeek v4 flash:  model="deepseek/deepseek-v4-flash"
  - GLM-47:             model="glm/glm-47"
  - vLLM / Ollama:      model="openai/<name>"

所有调用经过 call_llm() 统一方法，自动注入 api_base/api_key/extra_headers。
"""

import logging
import time
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)


def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[int] = None,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str:
    """
    调用 LLM 的统一入口。

    参数优先级：方法参数 > 项目设置 > 全局默认配置。
    返回模型响应的纯文本内容。
    """
    settings = get_settings()

    # 合并配置——显式参数优先
    model = model or settings.llm_model
    api_base = api_base or settings.llm_api_base
    api_key = api_key or settings.llm_api_key
    temperature = temperature if temperature is not None else settings.llm_temperature
    max_tokens = max_tokens or settings.llm_max_tokens
    timeout = timeout or settings.llm_timeout

    try:
        import litellm
    except ImportError:
        raise RuntimeError("litellm 未安装，请执行 pip install litellm")

    t0 = time.time()

    # 构建消息
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info("LLM 调用开始",
        extra={"task_id": task_id, "project_id": project_id,
               "model": model, "prompt_len": len(prompt)})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "api_base": api_base,
        "api_key": api_key,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout

    # 注入自定义 HTTP 头（如 GLM 需要 X-Auth-Token）
    if settings.llm_extra_headers:
        kwargs["extra_headers"] = settings.llm_extra_headers

    try:
        response = litellm.completion(**kwargs)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        logger.error("LLM 调用失败",
            extra={"task_id": task_id, "duration_ms": int(elapsed),
                   "error": str(e)})
        raise

    elapsed = (time.time() - t0) * 1000
    content = response.choices[0].message.content

    logger.info("LLM 调用完成",
        extra={"task_id": task_id, "duration_ms": int(elapsed),
               "response_len": len(content)})

    return content


def call_llm_with_retry(
    prompt: str,
    max_retries: Optional[int] = None,
    task_id: Optional[str] = None,
    **kwargs,
) -> str:
    """
    带自动重试的 LLM 调用。

    瞬时故障自动指数退避重试（5s → 15s → 45s），重试耗尽后抛出异常。
    """
    settings = get_settings()
    max_retries = max_retries if max_retries is not None else settings.llm_max_retries

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return call_llm(prompt=prompt, task_id=task_id, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = 5 * (3 ** attempt)  # 5s → 15s → 45s
                logger.warning(
                    f"LLM 调用重试 {attempt + 1}/{max_retries}",
                    extra={"task_id": task_id, "delay": delay, "error": str(e)},
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"LLM 调用重试耗尽（{max_retries}次）",
                    extra={"task_id": task_id, "final_error": str(e)},
                )
    raise last_error  # type: ignore


def verify_llm_connection(settings=None) -> bool:
    """健康检查：验证 LLM 接口连通性。"""
    if settings is None:
        settings = get_settings()
    try:
        result = call_llm(
            prompt="回复'OK'，只回复这两个字母。",
            max_tokens=5,
            timeout=10,
        )
        return "OK" in result
    except Exception:
        return False
```

- [ ] **Step 2: 编写 LLM 引擎测试（Mock litellm）**

```python
# backend/tests/unit/test_llm_engine.py
"""LLM 引擎测试——使用 Mock 避免真实 API 调用。"""

import pytest
from unittest.mock import MagicMock, patch
from app.engines.llm_engine import call_llm, verify_llm_connection


class TestCallLLM:
    """call_llm 基础测试。"""

    @patch("app.engines.llm_engine.litellm")
    def test_正常调用返回文本(self, mock_litellm, monkeypatch):
        """模拟 litellm 正常响应。"""
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这是 LLM 的回复"
        mock_litellm.completion.return_value = mock_response

        result = call_llm(prompt="测试问题")
        assert result == "这是 LLM 的回复"
        mock_litellm.completion.assert_called_once()

    @patch("app.engines.llm_engine.litellm")
    def test_调用参数传递正确(self, mock_litellm, monkeypatch):
        """验证 model/temperature/max_tokens 正确传递。"""
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        mock_litellm.completion.return_value = mock_response

        call_llm(prompt="Hello", model="glm/glm-47", temperature=0.5, max_tokens=4096)
        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["model"] == "glm/glm-47"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 4096

    @patch("app.engines.llm_engine.litellm")
    def test_system_prompt注入(self, mock_litellm, monkeypatch):
        """system_prompt 应作为第一个消息附加。"""
        monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        mock_litellm.completion.return_value = mock_response

        call_llm(prompt="Question", system_prompt="你是一个助手")
        messages = mock_litellm.completion.call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "你是一个助手"
        assert messages[1]["role"] == "user"
```

- [ ] **Step 3: Commit**

```bash
cd backend && python -m pytest tests/unit/test_llm_engine.py -v
git add backend/app/engines/llm_engine.py backend/tests/unit/test_llm_engine.py
git commit -m "feat: LLM引擎——litellm多Provider/自动重试/健康检查"
```

---

### Task 6: Wiki 引擎（页面 CRUD + Wikilink + Index）

**Files:**
- Create: `backend/app/engines/wiki_engine.py`
- Create: `backend/app/storage/file_storage.py`
- Test: `backend/tests/unit/test_wiki_engine.py`

- [ ] **Step 1: 编写文件原子操作模块**

```python
# backend/app/storage/file_storage.py
"""
文件系统操作封装——所有 Wiki 写入使用原子写入策略。

原子写入：先写入 .tmp 文件，再 os.replace()（原子操作）。
读者永远读到完整内容（旧版本或新版本），不会看到半写文件。
"""

import os
import re
import hashlib
import unicodedata
from pathlib import Path
from uuid import uuid4


# 允许上传的文件扩展名白名单
ALLOWED_EXTENSIONS = {
    ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}

# 分类型大小限制
SIZE_LIMITS = {
    ".pdf": 100 * 1024 * 1024,    # 100 MB
    ".epub": 100 * 1024 * 1024,
    ".wav": 200 * 1024 * 1024,    # 200 MB
    ".mp3": 200 * 1024 * 1024,
    ".pptx": 50 * 1024 * 1024,    # 50 MB
    ".xlsx": 50 * 1024 * 1024,
    ".docx": 50 * 1024 * 1024,
    ".xls": 50 * 1024 * 1024,
}
DEFAULT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB（纯文本类）
MAX_FILENAME_BYTES = 200  # UTF-8 编码后最大字节数
MAX_SUBDIR_DEPTH = 3      # raw/ 子目录最大深度


def sha256(text: str) -> str:
    """计算字符串的 SHA256（用于内容变更检测）。"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    """计算文件的 SHA256 摘要。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def atomic_write(path: Path, content: str):
    """原子写入——先写 .tmp，再 os.replace()。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))  # 原子重命名


def validate_extension(filename: str) -> bool:
    """文件扩展名白名单校验 + 双重扩展名检测。"""
    suffix = Path(filename).suffix.lower()
    # 双重扩展名检测：attack.pdf.exe
    stem = Path(filename).stem
    if Path(stem).suffix.lower() in ALLOWED_EXTENSIONS:
        return False
    if suffix not in ALLOWED_EXTENSIONS:
        return False
    if suffix == "":
        return False
    return True


def get_size_limit(filename: str) -> int:
    """根据文件类型返回大小上限。"""
    suffix = Path(filename).suffix.lower()
    return SIZE_LIMITS.get(suffix, DEFAULT_MAX_SIZE)


def sanitize_filename(filename: str) -> str:
    """
    文件名规范化。

    1. Unicode NFKC 规范化（全角→半角）
    2. 剥离路径分隔符
    3. 移除不可打印字符
    4. 去首尾空格和点
    5. 长度截断（保留扩展名）
    6. 空文件名兜底
    """
    filename = unicodedata.normalize("NFKC", filename)
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = re.sub(r"[^\x20-\x7E一-鿿　-〿＀-￯]", "_", filename)
    filename = filename.strip(" .")

    if len(filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        split = int(MAX_FILENAME_BYTES * 0.6)
        stem = stem.encode("utf-8")[:split].decode("utf-8", errors="ignore")
        filename = stem + "..." + suffix

    if not filename or filename.startswith("."):
        filename = f"unnamed_{uuid4().hex[:8]}{Path(filename).suffix}"

    return filename


def safe_subdir(base: Path, subdir: str) -> Path:
    """
    路径穿越防护——将用户输入的 subdir 规范化为安全路径。

    任何 ../ 尝试直接抛异常，不记录不处理。
    """
    cleaned = "/".join(
        s for s in subdir.strip("/").split("/")
        if s and s not in (".", "..")
    )
    candidate = (base / cleaned).resolve()
    if not str(candidate).startswith(str(base.resolve())):
        raise ValueError(f"路径穿越检测: {subdir}")
    return candidate
```

- [ ] **Step 2: 编写 Wiki 引擎**

```python
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
"""

import re
import os
import json
import logging
from pathlib import Path
from datetime import date
from typing import Optional

from app.storage.file_storage import atomic_write, sha256

logger = logging.getLogger(__name__)

# Wikilink 正则：[[PageName]] 或 [[PageName|显示文本]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


def read_page(path: Path) -> str:
    """读取 Wiki 页面内容。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_page(path: Path, content: str):
    """原子写入 Wiki 页面。"""
    atomic_write(path, content)


def extract_wikilinks(content: str) -> list[str]:
    """从页面内容中提取所有 [[WikiLink]] 目标名称。"""
    return [m[0].strip() for m in WIKILINK_PATTERN.findall(content)]


def all_wiki_pages(wiki_dir: Path) -> set[str]:
    """返回 wiki/ 目录下所有页面的 stem（小写，用于链接校验）。"""
    pages = set()
    for p in wiki_dir.rglob("*.md"):
        if p.name not in ("index.md", "log.md", "lint-report.md", "health-report.md"):
            pages.add(p.stem.lower())
    return pages


def validate_wikilinks(content: str, wiki_dir: Path) -> list[tuple[str, str]]:
    """
    校验页面中所有 wikilink 的有效性。

    返回 broken_links 列表：[(链接文本, 目标页面)]。
    """
    existing = all_wiki_pages(wiki_dir)
    broken = []
    for link_text in extract_wikilinks(content):
        if link_text.lower() not in existing:
            broken.append((link_text, link_text))
    return broken


def update_index(wiki_dir: Path, entry: str, section: str = "Sources"):
    """在 index.md 的指定 section 下添加条目。"""
    index_path = wiki_dir / "index.md"
    content = read_page(index_path)

    if not content:
        content = (
            "# Wiki Index\n\n"
            "## Overview\n- [Overview](overview.md) — 全局综合\n\n"
            "## Sources\n\n## Entities\n\n## Concepts\n\n## Syntheses\n"
        )

    section_marker = f"## {section}"
    if section_marker in content:
        content = content.replace(section_marker + "\n", section_marker + "\n" + entry + "\n")
    else:
        content += f"\n{section_marker}\n{entry}\n"

    write_page(index_path, content)


def remove_from_index(wiki_dir: Path, stem: str, section: str = "Sources"):
    """从 index.md 中移除指定条目。"""
    index_path = wiki_dir / "index.md"
    content = read_page(index_path)
    # 按行过滤，删除含该 stem 的行
    lines = content.split("\n")
    filtered = [l for l in lines if f"({section.lower()}/{stem}.md)" not in l]
    write_page(index_path, "\n".join(filtered))


def append_log(wiki_dir: Path, entry: str):
    """向 wiki/log.md 追加日志条目。"""
    log_path = wiki_dir / "log.md"
    existing = read_page(log_path)
    new_content = entry.strip() + "\n\n" + existing
    write_page(log_path, new_content)


def overview_hash(wiki_dir: Path) -> str:
    """计算 overview.md 的 SHA256（用于缓存判定）。"""
    overview_path = wiki_dir / "overview.md"
    return sha256(read_page(overview_path)) if overview_path.exists() else ""


def cleanup_stale_tmp(wiki_dir: Path):
    """清理残留的 .tmp 文件（写入过程中崩溃遗留）。"""
    for tmp in wiki_dir.rglob("*.tmp"):
        tmp.unlink()
        logger.info(f"清理残留临时文件: {tmp.relative_to(wiki_dir)}")
```

- [ ] **Step 3: 编写 Wiki 引擎测试**

```python
# backend/tests/unit/test_wiki_engine.py
"""Wiki 引擎测试。"""

import pytest
from pathlib import Path
from app.engines.wiki_engine import (
    extract_wikilinks, all_wiki_pages, validate_wikilinks,
    update_index, append_log,
)
from app.storage.file_storage import atomic_write


class TestWikilinkExtraction:
    """Wikilink 提取测试。"""

    def test_基本链接(self):
        """[[PageName]] 应被提取。"""
        content = "参见 [[Transformer]] 和 [[Self-Attention]]"
        links = extract_wikilinks(content)
        assert "Transformer" in links
        assert "Self-Attention" in links

    def test_别名链接(self):
        """[[PageName|显示文本]] 应提取目标名称而非显示文本。"""
        content = "[[Attention|注意力机制]] 是核心概念"
        links = extract_wikilinks(content)
        assert "Attention" in links
        assert "注意力机制" not in links

    def test_无链接(self):
        """无 wikilink 的内容返回空列表。"""
        content = "这是普通文本，没有链接。"
        assert extract_wikilinks(content) == []

    def test_多行链接(self):
        """跨行的 wikilink 都应被提取。"""
        content = "- [[A]]\n- [[B]]\n- [[C]]\n"
        assert len(extract_wikilinks(content)) == 3


class TestValidateWikilinks:
    """Wikilink 验证测试。"""

    def test_有效链接(self, tmp_path):
        """链接目标存在时不应报告 broken。"""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "Transformer.md").write_text("")
        broken = validate_wikilinks("参见 [[Transformer]]", wiki_dir)
        assert broken == []

    def test_无效链接(self, tmp_path):
        """链接目标不存在时应报告。"""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        broken = validate_wikilinks("参见 [[NonExistent]]", wiki_dir)
        assert len(broken) == 1
        assert broken[0][0] == "NonExistent"


class TestIndexUpdate:
    """Index 更新测试。"""

    def test_添加条目(self, tmp_path):
        """index.md 应包含新条目。"""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        update_index(wiki_dir, "- [测试](sources/test.md) — 摘要")
        content = (wiki_dir / "index.md").read_text()
        assert "测试" in content
        assert "sources/test.md" in content

    def test_首次创建index(self, tmp_path):
        """空目录首次调用应创建完整 index.md。"""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        update_index(wiki_dir, "- [首个](sources/first.md)")
        content = (wiki_dir / "index.md").read_text()
        assert "Wiki Index" in content
        assert "Sources" in content


class TestAppendLog:
    """操作日志测试。"""

    def test_追加日志(self, tmp_path):
        """新条目应排在最前面。"""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        append_log(wiki_dir, "## [2026-05-09] ingest | Test")
        append_log(wiki_dir, "## [2026-05-09] query | Query")
        content = (wiki_dir / "log.md").read_text()
        assert content.index("query") < content.index("ingest")  # 新条目在前
```

- [ ] **Step 4: Commit**

```bash
cd backend && python -m pytest tests/unit/test_wiki_engine.py tests/unit/test_file_storage.py -v
git add backend/app/engines/wiki_engine.py backend/app/storage/file_storage.py backend/tests/unit/test_wiki_engine.py
git commit -m "feat: Wiki引擎——页面CRUD/wikilink提取验证/index维护/原子写入"
```

---

### Task 7: Convert 引擎 + Graph 引擎 + Lock 管理器（关键代码）

**说明**：ConvertEngine、GraphEngine、LockManager 三个引擎的完整代码见设计文档。这里仅列出测试用例和关键接口签名以保持计划精简。

**Files:**
- Create: `backend/app/engines/convert_engine.py`
- Create: `backend/app/engines/graph_engine.py`
- Create: `backend/app/services/lock_manager.py`
- Test: `backend/tests/unit/test_convert_engine.py`
- Test: `backend/tests/unit/test_graph_engine.py`
- Test: `backend/tests/unit/test_lock_manager.py`

**关键接口签名**（实现参考设计文档对应章节）：

```python
# convert_engine.py
class ConvertEngine:
    def convert(self, file_path: Path, source_hint: str = "auto") -> str: ...
    def _detect_backends(self) -> dict: ...
    def _quality_check(self, text: str, original: Path) -> tuple[bool, str]: ...

# graph_engine.py
class GraphEngine:
    def build(self, wiki_dir: Path, graph_dir: Path) -> dict: ...
    def extract_links(self, wiki_dir: Path) -> list[dict]: ...
    def infer_edges(self, wiki_dir: Path, pages: list) -> list[dict]: ...
    def community_detection(self, nodes: list, edges: list) -> dict: ...
    def export_g6_json(self, nodes: list, edges: list) -> dict: ...

# lock_manager.py
class LockManager:
    def __init__(self, data_dir: Path): ...
    def acquire_project_write(self, project_id: str, timeout: float = 300) -> FileLock: ...
    def acquire_page_lock(self, project_id: str, page_path: str, mode="rw") -> FileLock: ...
    def acquire_directory_lock(self, project_id: str, dir_path: str, timeout=5) -> FileLock: ...
    def acquire_index_lock(self, project_id: str) -> FileLock: ...
    def release(self, lock: FileLock): ...
```

- [ ] **Commit**

```bash
git add backend/app/engines/ backend/app/services/lock_manager.py backend/tests/unit/
git commit -m "feat: Convert/Graph/Lock引擎——多后端转换/G6图谱/并发锁"
```

---

## Phase 3: 后端 API 路由（CRUD 模式）

### Task 8-13: API 路由实现模式

**模式说明**：以下 6 个 API 路由模块遵循统一的 CRUD 模式：

```
Router 层：参数校验 → 权限检查 → 调用 Service → 返回响应
Service 层：编排业务逻辑 → 调用 Engine → 写审计日志 → 返回结果
```

**文件清单（每个 Task 包含 Create 文件 + Test 文件）**：

| Task | 路由文件 | Service 文件 | 测试文件 |
|------|---------|-------------|---------|
| 8 | `api/projects.py` | `services/project_service.py` | `tests/unit/test_projects.py` |
| 9 | `api/files.py` | `services/file_service.py` | `tests/unit/test_files.py` |
| 10 | `api/ingestion.py` | `services/ingest_service.py` | `tests/unit/test_ingestion.py` |
| 11 | `api/knowledge.py` | `services/query_service.py` `services/page_service.py` | `tests/unit/test_knowledge.py` |
| 12 | `api/graph.py` | `services/graph_service.py` | `tests/unit/test_graph.py` |
| 13 | `api/maintenance.py` | `services/backup_service.py` | `tests/unit/test_maintenance.py` |

**统一实现模板**（以 Task 9 files.py 为例，其余 Task 参照此模板）：

```python
# backend/app/api/files.py
"""
文件管理 API 路由。

权限：Viewer 可查看/下载，Editor+ 可上传/删除/移动/目录管理。
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from typing import Optional
from app.api.deps import get_current_user, get_project_context
from app.services.file_service import FileService
from app.storage.database import get_db

router = APIRouter()


@router.get("/files")
async def list_files(
    project_id: str = Query(...),
    dir: str = Query(""),
    search: str = Query(""),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """
    获取项目文件列表。

    支持按子目录过滤、文件名搜索、offset/limit 分页。
    Viewer+ 均可访问。
    """
    ctx = get_project_context(project_id, user)  # 校验项目权限
    db = get_db("users")
    service = FileService(db)
    return service.list_files(project_id, dir=dir, search=search, offset=offset, limit=limit)


@router.post("/files/upload")
async def upload_file(
    project_id: str = Form(...),
    subdir: str = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传单个文件——需要 Editor+ 权限。"""
    ctx = get_project_context(project_id, user)
    if ctx["role"] not in ("owner", "editor"):
        raise HTTPException(403, "需要 Editor 或以上权限")
    # ... 实现细节
```

**测试模式**（每个 API 模块至少包含 3 类测试）：

```python
# tests/unit/test_files.py
class TestListFiles:
    def test_空目录返回空列表(self): ...
    def test_分页返回正确数量(self): ...
    def test_搜索过滤(self): ...

class TestUploadFile:
    def test_上传成功(self): ...
    def test_Viewer无权限拒绝(self): ...
    def test_扩展名白名单外拒绝(self): ...
    def test_文件超大拒绝_413(self): ...

class TestDeleteFile:
    def test_Owner删除成功(self): ...
    def test_Viewer删除拒绝(self): ...
    def test_级联清理wiki页(self): ...
```

- [ ] **分 Task Commit**

```bash
# Task 8
git add backend/app/api/projects.py backend/app/services/project_service.py backend/tests/unit/test_projects.py
git commit -m "feat: 项目管理API——CRUD/成员管理/设置"

# Task 9
git add backend/app/api/files.py backend/app/services/file_service.py backend/tests/unit/test_files.py
git commit -m "feat: 文件管理API——上传/下载/目录/批量"

# Task 10-13: 同上模式
```

---

## Phase 4: 后端高级特性

### Task 14: 摄入任务队列（持久化）

**Files:**
- Modify: `backend/app/services/task_queue.py`（基于数据库 task_queue 表）
- Test: `backend/tests/unit/test_task_queue.py`

关键实现要点（参考设计文档任务队列章节）：
- `create_task()` → 写入 SQLite task_queue 表 + 加入内存队列
- `recover_tasks_on_startup()` → 加载 queued/running 任务，running 重置为 queued
- 双写原则：状态变更先写 SQLite 再更新内存
- 过期清理：completed/failed 保留 7 天

### Task 15: 审计日志 + 应用日志集成

**Files:**
- Create: `backend/app/services/audit_service.py`
- Test: `backend/tests/unit/test_audit.py`

### Task 16: 全局 Admin API

**Files:**
- Create: `backend/app/api/admin.py`
- Test: `backend/tests/unit/test_admin.py`

---

## Phase 5: 前端基础架构

### Task 17: Vue3 项目脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`

```bash
cd frontend && npm create vite@latest . -- --template vue-ts
npm install vue-router@4 pinia axios markdown-it dompurify @antv/g6
npm install -D @types/markdown-it @types/dompurify vitest @vue/test-utils
```

### Task 18: Router + 导航守卫

**Files:**
- Create: `frontend/src/router/index.ts`

```typescript
// frontend/src/router/index.ts
/**
 * Vue Router 路由配置。
 *
 * 路由结构：
 *   /login                  — 登录页
 *   /                        — 重定向到上次访问项目
 *   /:projectId              — 知识库主页（源文件 + 查询）
 *   /:projectId/graph        — 知识图谱
 *   /:projectId/settings     — 项目设置
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue') },
  {
    path: '/:projectId',
    component: () => import('@/views/AppShell.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Knowledge', component: () => import('@/views/KnowledgeBaseView.vue') },
      { path: 'graph', name: 'Graph', component: () => import('@/views/GraphView.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/SettingsView.vue') },
    ],
  },
  { path: '/', redirect: '/default' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局导航守卫——未登录跳 /login
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.path === '/login') return true

  if (!auth.isAuthenticated) {
    // 尝试用 localStorage 的 token 初始化
    await auth.initialize()
  }

  if (!auth.isAuthenticated && to.meta.requiresAuth) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
```

### Task 19: Axios 客户端 + 拦截器

**Files:**
- Create: `frontend/src/api/client.ts`

```typescript
// frontend/src/api/client.ts
/**
 * 统一 Axios 实例——JWT 自动注入、401 自动刷新、错误统一处理。
 *
 * 所有 API 请求通过此模块发起，组件不直接 import axios。
 */

import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// 全局活跃请求计数器（用于顶部 Loading 条）
export const activeRequests = ref(0)

const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器——自动附加 JWT
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  activeRequests.value++
  return config
})

// 响应拦截器——401 自动刷新 Token
client.interceptors.response.use(
  (response) => { activeRequests.value--; return response },
  async (error: AxiosError) => {
    activeRequests.value--
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      try {
        await auth.refreshToken()
        return client.request(error.config!)  // 重试原请求
      } catch {
        auth.logout()
        router.push('/login')
      }
    }
    return Promise.reject(error)
  },
)

export default client
```

### Task 20: Pinia Stores（auth + project）

**Files:**
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/stores/project.ts`

### Task 21: Markdown 渲染 + XSS 防护

**Files:**
- Create: `frontend/src/lib/markdown.ts`

```typescript
// frontend/src/lib/markdown.ts
/**
 * Markdown 渲染 Pipeline——markdown-it 解析 → DOMPurify 清洗 → v-html 挂载。
 */

import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,       // 禁用 raw HTML（防 XSS）
  linkify: true,
  breaks: true,
  typographer: false, // 中文内容禁用智能引号
})

export function renderMarkdown(raw: string, projectId: string): string {
  // 预处理：[[PageName]] → 安全链接
  const withLinks = raw
    .replace(/\[\[([^\]|]+)\]\]/g, (_, page) =>
      `[${page.trim()}](/projects/${projectId}/pages/${encodeURIComponent(page.trim())})`)
    .replace(/\[\[([^\]]+)\|([^\]]+)\]\]/g, (_, page, text) =>
      `[${text.trim()}](/projects/${projectId}/pages/${encodeURIComponent(page.trim())})`)

  // markdown → HTML
  const html = md.render(withLinks)

  // DOMPurify 清洗（标签/属性/URI 三层白名单）
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['h1','h2','h3','h4','h5','h6','p','br','hr','ul','ol','li',
      'blockquote','pre','code','strong','em','s','del','ins','mark',
      'a','img','table','thead','tbody','tr','th','td','span','div'],
    ALLOWED_ATTR: ['href','target','rel','src','alt','title','class','id'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
  })
}
```

---

## Phase 6: 前端视图组件（Vue 组件模板模式）

### Task 22-27: Vue 视图实现

**模式说明**：Vue 组件遵循统一模式：`<script setup lang="ts">` + `<template>` + `<style scoped>`。

| Task | 组件 | 说明 |
|------|------|------|
| 22 | `views/AppShell.vue` `layout/Sidebar.vue` `layout/ProjectSwitcher.vue` | 应用壳 + 导航 + 项目切换 |
| 23 | `views/LoginView.vue` | 登录表单 |
| 24 | `views/KnowledgeBaseView.vue` `files/DirTree.vue` `files/FileList.vue` | 文件管理器 |
| 25 | `views/GraphView.vue` `graph/GraphCanvas.vue` `graph/FilterPanel.vue` | AntV G6 图谱 |
| 26 | `views/SettingsView.vue` | 项目设置 + 审计日志 |
| 27 | `common/*.vue` | ConfirmDialog / ProgressBar / EmptyState |

统一组件模板：

```vue
<!-- 示例：views/LoginView.vue -->
<script setup lang="ts">
/**
 * 登录页面——用户名 + 密码 → 获取 Token → 跳转项目列表。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = router.currentRoute.value.query.redirect as string || '/'
    router.push(redirect)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form @submit.prevent="handleLogin" class="login-form">
      <h1>🧠 LLM Wiki</h1>
      <p class="subtitle">知识从不丢失</p>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <input v-model="username" placeholder="用户名" required />
      <input v-model="password" type="password" placeholder="密码" required />
      <button type="submit" :disabled="loading">
        {{ loading ? '登录中...' : '登录' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F7F6F2;
}
/* ... 完整样式参考设计文档暖奶油配色 ... */
</style>
```

---

## Phase 7: 测试、集成与部署

### Task 28: 轮询 Composable

**Files:**
- Create: `frontend/src/composables/useTaskPolling.ts`
- Test: `frontend/tests/composables/useTaskPolling.test.ts`

```typescript
// frontend/src/composables/useTaskPolling.ts
/**
 * 自适应轮询 composable——递归 setTimeout，请求不重叠。
 */

import { ref, onUnmounted } from 'vue'
import { ingestionApi } from '@/api/ingestion'

function getPollingInterval(step: number, status: string): number {
  if (status === 'queued') return 5000
  switch (step) {
    case 1: return 3000
    case 2: return 2000  // LLM 调用最需要感知进度
    case 3: case 4: return 3000
    case 5: return 5000  // 图谱慢
    default: return 3000
  }
}

export function useTaskPolling(taskId: string) {
  const task = ref<TaskStatus | null>(null)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0

  async function poll() {
    try {
      const result = await ingestionApi.getStatus(taskId)
      task.value = result
      error.value = null
      retryCount = 0  // 成功后重置退避

      if (result.status === 'completed' || result.status === 'failed') return // 终态
      timer = setTimeout(poll, getPollingInterval(result.step, result.status))
    } catch (e: any) {
      error.value = e.message
      retryCount++
      const backoff = Math.min(3000 * Math.pow(2, retryCount), 30000)
      timer = setTimeout(poll, backoff)
    }
  }

  function start() { poll() }
  function stop() { if (timer) { clearTimeout(timer); timer = null } }
  onUnmounted(stop)

  return { task, error, start, stop }
}
```

### Task 29: 端到端测试 + Nginx 部署配置

**Files:**
- Create: `deploy/nginx.conf`
- Create: `deploy/docker-compose.yml`
- Create: `frontend/tests/e2e/`

---

## 实现顺序建议

按依赖关系分 7 个里程碑执行：

```
M1 (Task 1-3):   后端基础——启动可运行的健康检查端点
M2 (Task 4-7):   后端核心——认证可用、引擎就绪
M3 (Task 8-13):  后端 API——全部 REST 端点可用
M4 (Task 14-16): 后端高级——任务持久化、审计、Admin
M5 (Task 17-21): 前端基础——路由、Store、API Client、Markdown
M6 (Task 22-27): 前端视图——完整 UI
M7 (Task 28-29): 集成测试 + 部署
```

每个 M 里程碑完成后可进行集成验证。测试覆盖要求：

- **后端单测覆盖率 > 80%**（pytest + pytest-cov）
- **前端组件测试**（每个 view 至少 3 个测试用例）
- **API 集成测试**（关键 Happy Path + 权限拒绝 + 并发冲突）

---

**Plan complete.** 共 29 个 Task，7 个里程碑，覆盖设计文档全部需求。代码中所有注释使用中文，每个模块有对应的测试文件。

