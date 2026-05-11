"""
文件转换引擎——markitdown 通用转换 + 多后端 PDF 支持。

后端优先级（PDF）：
  1. marker-pdf（复杂排版，需 GPU）
  2. pymupdf4llm（通用 PDF，速度快）
  3. markitdown（fallback）

非 PDF 格式（docx/pptx/xlsx/html/txt 等）直接使用 markitdown。
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 需要转换的非 Markdown 格式
CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}


def _has_chinese(text: str) -> bool:
    """检测文本是否包含中文字符。"""
    return bool(re.search(r'[一-鿿]', text))


def _has_chinese_filename(path: Path) -> bool:
    """检测文件名是否包含中文。"""
    return _has_chinese(path.name)


class ConvertEngine:
    """多后端文件转换引擎。"""

    def __init__(self):
        self._backends = self._detect_backends()

    def _detect_backends(self) -> dict:
        """检测已安装的转换后端。"""
        backends = {"markitdown": True}  # 必装

        # 检测可选后端
        for name, module_path in [
            ("pymupdf4llm", "pymupdf4llm"),
            ("marker", "marker.convert"),
            ("arxiv2md", "arxiv2markdown"),
        ]:
            try:
                __import__(module_path)
                backends[name] = True
                logger.info(f"可选转换后端已安装: {name}")
            except ImportError:
                backends[name] = False

        return backends

    def convert(self, file_path: Path, source_hint: str = "auto") -> str:
        """
        将文件转换为 Markdown 文本。

        Args:
            file_path: 源文件路径
            source_hint: 来源提示（"arxiv" 尝试用 arxiv2markdown）

        Returns:
            转换后的 Markdown 文本
        """
        suffix = file_path.suffix.lower()

        if suffix == ".md":
            return file_path.read_text(encoding="utf-8")

        if suffix == ".pdf":
            return self._convert_pdf(file_path, source_hint)

        if suffix in CONVERTIBLE_EXTENSIONS:
            return self._convert_with_markitdown(file_path)

        raise ValueError(f"不支持的文件格式: {suffix}")

    def _convert_pdf(self, file_path: Path, source_hint: str) -> str:
        """PDF 转换——按优先级尝试多个后端。"""
        errors = []

        # 检测是否需要高质量转换
        need_high_quality = self._detect_complex_layout(file_path)

        if source_hint == "arxiv" and self._backends.get("arxiv2md"):
            try:
                return self._convert_with_arxiv(file_path)
            except Exception as e:
                errors.append(f"arxiv2md: {e}")

        # 后端优先级
        if need_high_quality and self._backends.get("marker"):
            try:
                return self._convert_with_marker(file_path)
            except Exception as e:
                errors.append(f"marker: {e}")

        if self._backends.get("pymupdf4llm"):
            try:
                return self._convert_with_pymupdf(file_path)
            except Exception as e:
                errors.append(f"pymupdf4llm: {e}")

        # markitdown fallback
        try:
            return self._convert_with_markitdown(file_path)
        except Exception as e:
            errors.append(f"markitdown: {e}")

        raise RuntimeError(f"所有 PDF 转换后端均失败: {'; '.join(errors)}")

    def _detect_complex_layout(self, file_path: Path) -> bool:
        """检测 PDF 是否包含复杂排版（多栏、表格、中文等）。"""
        size_mb = file_path.stat().st_size / (1024 * 1024)
        # 大文件（>5MB）或中文文件名 → 可能需要高质量转换
        if size_mb > 5:
            return True
        if _has_chinese_filename(file_path):
            return True
        return False

    def _convert_with_markitdown(self, file_path: Path) -> str:
        """使用 markitdown 进行转换。"""
        try:
            from markitdown import MarkItDown
        except ImportError:
            raise RuntimeError("markitdown 未安装，请执行: pip install markitdown")

        md = MarkItDown(enable_plugins=False)
        result = md.convert(str(file_path))
        text = result.text_content

        # 质量检查
        ok, reason = self._quality_check(text, file_path)
        if not ok:
            logger.warning(f"markitdown 输出质量不达标: {reason}", extra={"file": str(file_path)})
            # 不理想的输出也返回（已经是 fallback）
        return text

    def _convert_with_pymupdf(self, file_path: Path) -> str:
        """使用 pymupdf4llm 转换 PDF。"""
        import pymupdf4llm
        return pymupdf4llm.to_markdown(str(file_path))

    def _convert_with_marker(self, file_path: Path) -> str:
        """使用 marker-pdf 转换高质量 PDF。"""
        from marker.convert import convert_single_pdf
        full_text, _ = convert_single_pdf(str(file_path))
        return str(full_text)

    def _convert_with_arxiv(self, file_path: Path) -> str:
        """使用 arxiv2markdown 转换 arXiv 论文。"""
        from arxiv2markdown import Arxiv2Markdown
        a2m = Arxiv2Markdown(str(file_path))
        return a2m.to_markdown()

    def _quality_check(self, text: str, original: Path) -> tuple[bool, str]:
        """
        转换质量检查——不达标时调用方可以换后端重试。

        Returns:
            (是否合格, 原因)
        """
        # 1. 输出太短（<100 字符但原文件 >1MB）→ 可能转换失败
        file_size = os.path.getsize(original)
        if len(text) < 100 and file_size > 1024 * 1024:
            return False, "output_too_short"

        # 2. 乱码检测（不可打印字符比例 >30%）
        printable = sum(c.isprintable() or c in "\n\r\t" for c in text)
        if len(text) > 0 and printable / len(text) < 0.7:
            return False, "garbled_output"

        # 3. 中文文档输出无中文字符
        if _has_chinese_filename(original) and not _has_chinese(text):
            return False, "chinese_missing"

        # 4. 纯图片引用（无实质文本）
        text_no_images = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        if len(text_no_images.strip()) < 200 and file_size > 500 * 1024:
            return False, "image_only"

        return True, "ok"

    def is_convertible(self, filename: str) -> bool:
        """检查文件是否需要/可以进行格式转换。"""
        suffix = Path(filename).suffix.lower()
        return suffix == ".md" or suffix in CONVERTIBLE_EXTENSIONS
