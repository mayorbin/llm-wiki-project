# backend/app/storage/file_storage.py
"""
文件系统操作封装——原子写入、上传安全校验、路径穿越防护。

所有 Wiki 写入使用原子写入策略（先 .tmp 再 os.replace），
保证读者永远读到完整内容（旧版本或新版本，不会看到半写文件）。
"""

import os
import re
import hashlib
import unicodedata
from pathlib import Path
from uuid import uuid4


# ── 文件上传安全常量 ──

# 允许上传的文件扩展名白名单
ALLOWED_EXTENSIONS: set[str] = {
    ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}

# 分类型大小限制（字节）
SIZE_LIMITS: dict[str, int] = {
    ".pdf": 100 * 1024 * 1024,    # 100 MB
    ".epub": 100 * 1024 * 1024,
    ".wav": 200 * 1024 * 1024,    # 200 MB
    ".mp3": 200 * 1024 * 1024,
    ".pptx": 50 * 1024 * 1024,    # 50 MB
    ".xlsx": 50 * 1024 * 1024,
    ".docx": 50 * 1024 * 1024,
    ".xls": 50 * 1024 * 1024,
}
DEFAULT_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB（纯文本类默认）
MAX_FILENAME_BYTES: int = 200
MAX_SUBDIR_DEPTH: int = 3


def sha256(text: str) -> str:
    """计算字符串的 SHA256 摘要（取前 16 个十六进制字符）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    """计算文件的 SHA256 摘要。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def atomic_write(path: Path, content: str):
    """原子写入——先写 .tmp 文件，再通过 os.replace() 原子重命名。

    保证写入过程中崩溃不会损坏目标文件（残留 .tmp 文件由 health check 定期清理）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))


def validate_extension(filename: str) -> bool:
    """文件扩展名校验——白名单 + 双重扩展名检测。

    Returns:
        True 如果扩展名在白名单内且非双重扩展名伪装。
    """
    suffix = Path(filename).suffix.lower()
    if suffix == "":
        return False
    if suffix not in ALLOWED_EXTENSIONS:
        return False

    # 双重扩展名检测：attack.pdf.exe → stem="attack.pdf" → .pdf 在白名单内 → 拒绝
    stem = Path(filename).stem
    if Path(stem).suffix.lower() in ALLOWED_EXTENSIONS:
        return False

    return True


def get_size_limit(filename: str) -> int:
    """根据文件类型返回大小上限（字节）。"""
    suffix = Path(filename).suffix.lower()
    return SIZE_LIMITS.get(suffix, DEFAULT_MAX_SIZE)


def sanitize_filename(filename: str) -> str:
    """
    文件名规范化。

    处理步骤：
    1. Unicode NFKC 规范化（全角→半角，兼容字符→标准形式）
    2. 剥离路径分隔符（/ 和 \\ 替换为 _）
    3. 移除 Windows 禁用字符（NFKC 可能将全角符号转为半角禁符）
    4. 移除不可打印字符
    5. 去首尾空格和点（Windows 不允许）
    6. UTF-8 字节长度截断（保留扩展名）
    7. 空文件名兜底
    """
    filename = unicodedata.normalize("NFKC", filename)
    filename = filename.replace("/", "_").replace("\\", "_")
    # Windows 文件名禁用字符（NFKC 将全角 ：＂＊？＜＞｜ 等转为半角禁符）
    for ch in '<>:"|?*':
        filename = filename.replace(ch, '_')
    filename = re.sub(r"[^\x20-\x7E一-鿿　-〿＀-￯]", "_", filename)
    filename = filename.strip(" .")

    # 长度截断
    if len(filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        p = Path(filename)
        stem = p.stem
        suffix = p.suffix
        split_bytes = int(MAX_FILENAME_BYTES * 0.6)
        stem = stem.encode("utf-8")[:split_bytes].decode("utf-8", errors="ignore")
        filename = stem + "..." + suffix

    # 空文件名兜底
    if not filename or filename.startswith("."):
        filename = f"unnamed_{uuid4().hex[:8]}{Path(filename).suffix}"

    return filename


def safe_subdir(base: Path, subdir: str) -> Path:
    """
    路径穿越防护——将用户输入的 subdir 规范化为安全路径。

    任何 ../ 或 ..\\ 尝试直接抛出 ValueError，不记录、不处理。
    子目录深度限制为 MAX_SUBDIR_DEPTH 层。
    """
    parts = [s for s in subdir.strip("/").split("/") if s]
    # 任何 .. 组件直接拒绝，不静默过滤
    if ".." in parts:
        raise ValueError(f"路径穿越检测: {subdir}")
    cleaned = "/".join(s for s in parts if s != ".")

    # 确保 base 为绝对路径，Windows 下相对/绝对混用会导致
    # resolve() / relative_to() 行为不一致
    base = base.resolve()
    candidate = (base / cleaned).resolve()

    # 必须在 base 目录之下
    if not str(candidate).startswith(str(base)):
        raise ValueError(f"路径穿越检测: {subdir}")

    # 深度限制
    relative = candidate.relative_to(base)
    depth = len(relative.parts) if str(relative) != "." else 0
    if depth > MAX_SUBDIR_DEPTH:
        raise ValueError(f"子目录深度超过限制（最多 {MAX_SUBDIR_DEPTH} 层）: {subdir}")

    return candidate
