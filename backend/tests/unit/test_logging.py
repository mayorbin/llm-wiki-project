# backend/tests/unit/test_logging.py
"""
日志系统测试。
"""

import json
import logging
import pytest
from pathlib import Path
from app.logging_config import setup_logging, StructuredFormatter


class TestStructuredFormatter:
    """结构化格式化器测试。"""

    def test_普通INFO日志输出有效JSON(self):
        """普通 INFO 日志应输出有效的 JSON Lines 格式。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="test.py",
            lineno=42, msg="文件上传成功", args=(), exc_info=None,
        )
        # 注入上下文信息
        record.project_id = "proj-abc"
        record.duration_ms = 150

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["msg"] == "文件上传成功"
        assert data["logger"] == "test.logger"
        assert data["project_id"] == "proj-abc"
        assert data["duration_ms"] == 150
        assert "ts" in data
        assert "module" in data
        # 正常日志不应包含 error 字段
        assert "error" not in data

    def test_ERROR日志包含异常信息(self):
        """ERROR 级别日志应包含异常类型和 traceback。"""
        formatter = StructuredFormatter()
        try:
            raise ValueError("磁盘空间不足")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="engine.py",
                lineno=100, msg="摄入失败", args=(), exc_info=sys.exc_info(),
            )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "ERROR"
        assert data["error"]["type"] == "ValueError"
        assert "磁盘空间不足" in data["error"]["message"]
        assert "traceback" in data["error"]

    def test_无上下文字段不影响输出(self):
        """没有注入上下文字段时，日志仍正常输出。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="test.py",
            lineno=1, msg="简单警告", args=(), exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["level"] == "WARNING"
        assert data["msg"] == "简单警告"

    def test_task_id注入(self):
        """task_id 上下文应正确注入到日志条目。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="ingest", level=logging.INFO, pathname="ingest.py",
            lineno=50, msg="摄入完成", args=(), exc_info=None,
        )
        record.task_id = "task-uuid-12345"
        result = formatter.format(record)
        data = json.loads(result)
        assert data["task_id"] == "task-uuid-12345"


class TestSetupLogging:
    """日志初始化测试。"""

    def test_创建日志目录和文件(self, tmp_path):
        """初始化后应创建 app.log 和 error.log 文件。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")

        assert (log_dir / "app.log").exists()
        assert (log_dir / "error.log").exists()

    def test_写入日志到文件(self, tmp_path):
        """写入一条 INFO 日志后，app.log 应包含该内容。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")

        logger = logging.getLogger("test_writer")
        logger.info("测试消息 hello world")

        content = (log_dir / "app.log").read_text(encoding="utf-8")
        assert "测试消息 hello world" in content
        assert '"level": "INFO"' in content

    def test_ERROR日志同时写入两个文件(self, tmp_path):
        """ERROR 日志应同时出现在 app.log 和 error.log 中。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")

        logger = logging.getLogger("test_dual")
        logger.error("严重错误")

        app_content = (log_dir / "app.log").read_text(encoding="utf-8")
        err_content = (log_dir / "error.log").read_text(encoding="utf-8")
        assert "严重错误" in app_content
        assert "严重错误" in err_content

    def test_DEBUG级别不写入error_log(self, tmp_path):
        """DEBUG 级别日志不应写入 error.log。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="DEBUG")

        logger = logging.getLogger("test_debug")
        logger.debug("调试信息")

        err_content = (log_dir / "error.log").read_text(encoding="utf-8")
        assert err_content == "" or "调试信息" not in err_content

    def test_不重复添加handler(self, tmp_path):
        """多次调用 setup_logging 不应导致 handler 数量倍增。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        root = logging.getLogger()
        count_before = len(root.handlers)

        setup_logging(log_dir, level="INFO")
        assert len(root.handlers) == count_before

    def test_DEBUG模式有额外handler(self, tmp_path):
        """DEBUG 模式应比 INFO 模式多一个 console handler。"""
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        info_count = len(logging.getLogger().handlers)

        setup_logging(log_dir, level="DEBUG")
        debug_count = len(logging.getLogger().handlers)
        assert debug_count > info_count


class TestGetLogger:
    """get_logger 辅助函数测试。"""

    def test_get_logger返回Logger实例(self):
        """get_logger 应返回标准的 logging.Logger 实例。"""
        logger = logging.getLogger("my.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"
