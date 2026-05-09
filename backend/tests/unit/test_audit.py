# backend/tests/unit/test_audit.py
"""审计日志服务测试。"""
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.audit_service import write_audit_log, query_audit_log


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-key-32chars-long-enough!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


def test_写入审计日志():
    write_audit_log("upload", "u_1", "张三", "p_1", "raw/test.pdf", "success")
    result = query_audit_log("p_1", limit=10)
    assert len(result["data"]) == 1


def test_查询按操作类型过滤():
    write_audit_log("upload", "u_1", "张三", "p_1", "a.pdf", "success")
    write_audit_log("delete", "u_2", "李四", "p_1", "b.pdf", "success")
    result = query_audit_log("p_1", action="upload", limit=10)
    assert len(result["data"]) == 1
    assert result["data"][0]["action"] == "upload"


def test_分页查询():
    for i in range(5):
        write_audit_log("ingest", "u_1", "张三", "p_1", f"file_{i}.md", "success")
    result = query_audit_log("p_1", limit=3)
    assert len(result["data"]) == 3
    assert result["pagination"]["has_more"] is True
