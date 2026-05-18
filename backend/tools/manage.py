#!/usr/bin/env python3
"""
LLM Wiki 管理工具。

用法:
  python tools/manage.py create-admin          # 交互式创建管理员
  python tools/manage.py create-admin --username admin --password <pwd>
  python tools/manage.py check                 # 检查系统状态
  python tools/manage.py reset-password --username <name> --new-password <pwd>
"""

import sys
import io
import uuid
import secrets
from pathlib import Path

# Windows 下强制 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 将 backend 目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings, get_settings, reset_settings
from app.storage.database import init_db, close_all_db
from app.services.auth_service import hash_password


def create_admin(username: str = None, password: str = None, display_name: str = ""):
    """创建管理员用户。用户不存在则创建，已存在则提升为 admin。"""
    settings = get_settings()

    # 确保数据库已初始化
    init_db(settings.data_dir)

    from app.storage.database import get_db
    db = get_db("users")

    # 交互式输入
    if not username:
        username = input("管理员用户名: ").strip()
    if not password:
        password = input("管理员密码: ").strip()
    if not display_name:
        display_name = input("显示名称 (可选): ").strip()

    if not username or not password:
        print("错误: 用户名和密码不能为空")
        sys.exit(1)

    if len(password) < 6:
        print("错误: 密码长度至少 6 位")
        sys.exit(1)

    # 检查用户是否已存在
    existing = db.execute(
        "SELECT id, role FROM users WHERE username = ?", (username,)
    ).fetchone()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        if existing["role"] == "admin":
            print(f"用户 {username} 已经是管理员 (id={existing['id']})")
            return
        # 提升为 admin
        db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))
        db.commit()
        print(f"已将 {username} 提升为管理员 (id={existing['id']})")
    else:
        user_id = f"u_{uuid.uuid4().hex[:12]}"
        pwd_hash = hash_password(password)
        db.execute(
            "INSERT INTO users (id, username, password_hash, display_name, role, created_at) "
            "VALUES (?, ?, ?, ?, 'admin', ?)",
            (user_id, username, pwd_hash, display_name, now),
        )
        db.commit()
        print(f"管理员创建成功: {username} (id={user_id})")

    close_all_db()


def reset_password(username: str, new_password: str):
    """重置用户密码。"""
    if not username or not new_password:
        print("错误: 需要 --username 和 --new-password 参数")
        sys.exit(1)

    if len(new_password) < 6:
        print("错误: 密码长度至少 6 位")
        sys.exit(1)

    settings = get_settings()
    init_db(settings.data_dir)

    from app.storage.database import get_db
    db = get_db("users")

    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        print(f"错误: 用户 {username} 不存在")
        sys.exit(1)

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), row["id"]),
    )
    db.commit()
    close_all_db()
    print(f"密码已重置: {username}")


def check_system():
    """检查系统状态。"""
    print("=" * 50)
    print("LLM Wiki 系统检查")
    print("=" * 50)

    settings = get_settings()

    # 1. 配置文件
    print("\n[配置]")
    print(f"  数据目录: {settings.data_dir}")
    print(f"  LLM 模型: {settings.llm_model}")
    print(f"  LLM 接口: {settings.llm_api_base}")
    print(f"  日志级别: {settings.log_level}")

    # 2. 数据目录
    data_dir = Path(settings.data_dir)
    print(f"\n[数据目录] {data_dir}")
    if data_dir.exists():
        print("  [OK] 目录存在")
    else:
        print("  [WARN] 目录不存在（首次启动自动创建）")

    # 3. 数据库
    print("\n[数据库]")
    try:
        init_db(settings.data_dir)
        from app.storage.database import get_db, close_all_db
        users_db = get_db("users")
        user_count = users_db.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
        admin_count = users_db.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'"
        ).fetchone()["cnt"]
        print(f"  用户数: {user_count}")
        print(f"  管理员数: {admin_count}")
        if admin_count == 0:
            print("  [WARN] 尚无管理员！运行: python tools/manage.py create-admin")
        close_all_db()
    except Exception as e:
        print(f"  [FAIL] 数据库错误: {e}")

    # 4. LLM 连通性
    print("\n[LLM 连通性]")
    try:
        from app.engines.llm_engine import verify_llm_connection
        if verify_llm_connection():
            print(f"  [OK] 连接成功 ({settings.llm_model})")
        else:
            print(f"  [FAIL] 连接失败 ({settings.llm_model})")
    except Exception as e:
        print(f"  [FAIL] 检测失败: {e}")

    # 5. 安全配置
    print("\n[安全]")
    if settings.secret_key:
        print(f"  [OK] secret_key 已设置 ({len(settings.secret_key)} 字符)")
    else:
        print("  [WARN] secret_key 未设置！JWT 签名将不安全")
        print(f"    生成随机密钥: {secrets.token_hex(32)}")
    if settings.llm_api_key:
        print(f"  [OK] llm_api_key 已设置 ({len(settings.llm_api_key)} 字符)")
    else:
        print("  [WARN] llm_api_key 未设置！LLM 调用将失败")

    print("\n" + "=" * 50)
    close_all_db()


def print_usage():
    print(__doc__)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_usage()
        sys.exit(0)

    cmd = args[0]

    if cmd == "create-admin":
        username = None
        password = None
        i = 1
        while i < len(args):
            if args[i] == "--username" and i + 1 < len(args):
                username = args[i + 1]; i += 2
            elif args[i] == "--password" and i + 1 < len(args):
                password = args[i + 1]; i += 2
            else:
                i += 1
        create_admin(username=username, password=password)

    elif cmd == "reset-password":
        username = None
        new_password = None
        i = 1
        while i < len(args):
            if args[i] == "--username" and i + 1 < len(args):
                username = args[i + 1]; i += 2
            elif args[i] == "--new-password" and i + 1 < len(args):
                new_password = args[i + 1]; i += 2
            else:
                i += 1
        reset_password(username=username, new_password=new_password)

    elif cmd == "check":
        check_system()

    else:
        print(f"未知命令: {cmd}")
        print_usage()
        sys.exit(1)
