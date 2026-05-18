# backend/app/storage/database.py
"""
SQLite 数据库管理模块。

数据库文件布局：
  - data/users.db   —— 用户、项目、项目成员、项目设置
  - data/tasks.db   —— 摄入任务队列
  - data/audit.db   —— 审计日志

所有连接在应用生命周期内复用。使用 WAL 模式提升并发读取性能，
启用外键约束保证数据完整性。
"""

import sqlite3
from pathlib import Path
from app.config import get_settings

# 数据库连接缓存（key=数据库名）
_connections: dict[str, sqlite3.Connection] = {}


def get_db(db_name: str = "users") -> sqlite3.Connection:
    """获取指定数据库的连接，首次访问时自动创建并启用 WAL 模式。"""
    global _connections
    if db_name in _connections:
        return _connections[db_name]

    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / f"{db_name}.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 查询结果按列名访问
    conn.execute("PRAGMA journal_mode=WAL")     # 提升并发读取性能
    conn.execute("PRAGMA foreign_keys=ON")       # 启用外键约束
    _connections[db_name] = conn
    return conn


def init_db(data_dir: str):
    """
    首次启动时初始化所有数据库表。

    使用 IF NOT EXISTS 确保幂等——多次调用不会重复创建。
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    # ── users.db：用户与项目 ──
    users_db = get_db("users")
    users_db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            username        TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            display_name    TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'user',
            is_active       INTEGER NOT NULL DEFAULT 1,
            deleted_at      TEXT,
            created_at      TEXT NOT NULL,
            last_login      TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            created_by  TEXT NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL,
            archived_at TEXT
        );

        -- 同一用户不能创建同名项目
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_name_owner
            ON projects(name, created_by);

        CREATE TABLE IF NOT EXISTS project_members (
            project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role        TEXT NOT NULL DEFAULT 'editor',
            joined_at   TEXT NOT NULL,
            PRIMARY KEY (project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS project_settings (
            project_id  TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            settings    TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL
        );
    """)

    # ── tasks.db：摄入任务队列 ──
    tasks_db = get_db("tasks")
    tasks_db.executescript("""
        CREATE TABLE IF NOT EXISTS task_queue (
            task_id       TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            action        TEXT NOT NULL,
            file_paths    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'queued',
            progress      INTEGER NOT NULL DEFAULT 0,
            error_code    TEXT,
            error_message TEXT,
            error_detail  TEXT,
            retry_count   INTEGER NOT NULL DEFAULT 0,
            max_retries   INTEGER NOT NULL DEFAULT 3,
            created_by    TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            started_at    TEXT,
            completed_at  TEXT,
            snapshot_dir  TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_task_project
            ON task_queue(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_task_created
            ON task_queue(created_at);
    """)

    # ── audit.db：审计日志 ──
    audit_db = get_db("audit")
    audit_db.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            action      TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            project_id  TEXT NOT NULL,
            target      TEXT NOT NULL,
            detail      TEXT,
            result      TEXT NOT NULL,
            error       TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_project_time
            ON audit_log(project_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_user
            ON audit_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action
            ON audit_log(action);
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
