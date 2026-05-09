# backend/app/storage/database.py
"""
数据库初始化模块（桩实现）。

Task 2 将替换为完整的 SQLAlchemy + SQLite 实现。
"""

import logging

logger = logging.getLogger(__name__)


def init_db(data_dir: str) -> None:
    """初始化数据库连接并确保表结构存在。

    Args:
        data_dir: 数据目录路径，用于确定数据库文件位置
    """
    # 桩实现：Task 2 将替换为真实实现
    logger.info("数据库初始化（桩）| data_dir=%s", data_dir)
