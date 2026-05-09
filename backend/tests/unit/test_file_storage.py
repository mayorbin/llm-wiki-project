# backend/tests/unit/test_file_storage.py
"""文件存储模块测试。"""

import pytest
from pathlib import Path
from app.storage.file_storage import (
    atomic_write, validate_extension, get_size_limit,
    sanitize_filename, safe_subdir, file_sha256, sha256,
)


class TestAtomicWrite:
    def test_基本写入(self, tmp_path):
        """原子写入应创建目标文件并包含正确内容。"""
        target = tmp_path / "test.md"
        atomic_write(target, "Hello Wiki")
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "Hello Wiki"

    def test_不存在的父目录自动创建(self, tmp_path):
        """目标路径的父目录不存在时应自动创建。"""
        target = tmp_path / "deep" / "nested" / "file.md"
        atomic_write(target, "deep content")
        assert target.exists()

    def test_多次写入覆盖(self, tmp_path):
        """连续两次写入，第二次应覆盖第一次。"""
        target = tmp_path / "doc.md"
        atomic_write(target, "v1")
        atomic_write(target, "v2")
        assert target.read_text(encoding="utf-8") == "v2"


class TestValidateExtension:
    def test_允许的md(self):
        assert validate_extension("readme.md") is True

    def test_允许的pdf(self):
        assert validate_extension("paper.pdf") is True

    def test_不允许的exe(self):
        assert validate_extension("virus.exe") is False

    def test_双重扩展名伪装(self):
        """attack.pdf.exe 应被拒绝（双重扩展名检测）。"""
        assert validate_extension("report.pdf.exe") is False

    def test_空扩展名拒绝(self):
        assert validate_extension("noextension") is False

    def test_大小写不敏感(self):
        assert validate_extension("DOCUMENT.PDF") is True


class TestGetSizeLimit:
    def test_PDF上限100MB(self):
        assert get_size_limit("doc.pdf") == 100 * 1024 * 1024

    def test_MD默认上限10MB(self):
        assert get_size_limit("readme.md") == 10 * 1024 * 1024

    def test_音频上限200MB(self):
        assert get_size_limit("recording.mp3") == 200 * 1024 * 1024


class TestSanitizeFilename:
    def test_正常文件名不变(self):
        assert sanitize_filename("论文-2025.pdf") == "论文-2025.pdf"

    def test_路径分隔符替换(self):
        """文件名中 / 或 \\ 应替换为 _。"""
        assert "/" not in sanitize_filename("etc/passwd.txt")
        assert "\\" not in sanitize_filename("..\\secret.txt")

    def test_去首尾空格和点(self):
        result = sanitize_filename("  file.txt  ")
        assert not result.startswith(" ")
        assert result.endswith(".txt")

    def test_空文件名兜底(self):
        result = sanitize_filename("")
        assert result.startswith("unnamed_")
        assert result != ""


class TestSafeSubdir:
    def test_正常子目录(self, tmp_path):
        base = tmp_path / "raw"
        base.mkdir()
        result = safe_subdir(base, "论文/2025")
        assert result == (base / "论文" / "2025").resolve()

    def test_路径穿越拒绝(self, tmp_path):
        """../ 尝试应直接抛出异常。"""
        base = (tmp_path / "raw").resolve()
        base.mkdir(parents=True)
        with pytest.raises(ValueError, match="路径穿越"):
            safe_subdir(base, "../../etc/passwd")

    def test_超过最大深度拒绝(self, tmp_path):
        """超过 3 层子目录应拒绝。"""
        base = (tmp_path / "raw").resolve()
        base.mkdir(parents=True)
        with pytest.raises(ValueError, match="深度超过限制"):
            safe_subdir(base, "a/b/c/d")
