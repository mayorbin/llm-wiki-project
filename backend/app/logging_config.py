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
from datetime import datetime, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler


class StructuredFormatter(logging.Formatter):
    """JSON Lines 结构化日志格式化器，方便 grep / jq / 日志聚合工具解析。"""

    def format(self, record: logging.LogRecord) -> str:
        # 手动构造 ISO8601 时间戳（含毫秒），避免 strftime 不支持 %(msecs)
        msecs = int((record.created % 1) * 1000)
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + f".{msecs:03d}"

        log_entry = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": f"{record.module}:{record.funcName}:{record.lineno}",
        }

        # 注入上下文字段（通过 logging adapter 或 extra 传入）
        for key in ("project_id", "user_id", "task_id", "request_id", "duration_ms"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # 异常信息（仅在 ERROR 级别记录完整堆栈）
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info).split("\n"),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(log_dir: Path, level: str = "INFO"):
    """
    初始化日志系统。

    handler 列表：
      - app.log:   结构化 JSON，50MB 轮转 × 10 个备份
      - error.log: 仅 ERROR+ 级别，20MB 轮转 × 5 个备份
      - stdout:    彩色可读格式（仅在 DEBUG 模式启用）
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    # 清除已存在的 handler（防止重复初始化）
    root.handlers.clear()

    # Handler 1: 全量日志 → app.log（DEBUG 及以上全收）
    app_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,              # 保留最近 10 个轮转文件
        encoding="utf-8",
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(StructuredFormatter())
    root.addHandler(app_handler)

    # Handler 2: 错误日志 → error.log（ERROR 和 CRITICAL）
    err_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=20 * 1024 * 1024,  # 20 MB
        backupCount=5,               # 保留最近 5 个轮转文件
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(StructuredFormatter())
    root.addHandler(err_handler)

    # Handler 3: 控制台输出（仅 DEBUG 模式，可读格式便于开发）
    if level.upper() == "DEBUG":
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s"
        ))
        root.addHandler(console)

    # 降低第三方库的日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取带模块名的 logger（等价于 logging.getLogger）。"""
    return logging.getLogger(name)
