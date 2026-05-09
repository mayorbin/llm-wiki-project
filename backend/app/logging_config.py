# backend/app/logging_config.py
"""
日志配置模块。

提供统一的日志初始化功能，支持控制台输出和文件轮转。
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    """初始化日志系统。

    配置控制台和文件双通道输出，使用标准 Python logging 模块。

    Args:
        log_dir: 日志文件存储目录
        level: 日志级别（DEBUG | INFO | WARNING | ERROR）
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 解析日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有的处理器，避免重复添加
    root_logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    file_handler = logging.FileHandler(
        log_dir / "app.log", encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 降低第三方库日志噪音
    for lib in ("uvicorn", "httpx", "watchfiles"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成 | level=%s | dir=%s", level, log_dir)
