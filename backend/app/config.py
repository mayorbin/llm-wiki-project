# backend/app/config.py
"""
配置管理模块。

配置加载优先级（高→低）：
1. 环境变量 LLM_WIKI_*
2. .env 文件
3. config.yaml
4. 代码默认值

用法：
    from app.config import get_settings
    settings = get_settings()
    settings.validate_required()  # 启动时校验必填项
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局应用配置，所有字段可通过环境变量 LLM_WIKI_<FIELD> 覆盖。"""

    # ── 应用基础 ──
    app_name: str = "LLM Wiki"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR

    # ── 数据目录 ──
    data_dir: str = "./data"

    # ── 默认 LLM 配置（全局默认，项目可覆盖） ──
    llm_provider: str = "openai_compatible"
    llm_model: str = "deepseek/deepseek-v4-flash"
    llm_api_base: str = ""  # 空则使用 litellm 内置的 provider 默认地址
    llm_api_key: str = ""
    llm_temperature: float = 0.3
    llm_max_tokens: int = 8192
    llm_timeout: int = 120  # 秒
    llm_max_retries: int = 3
    llm_extra_headers: dict = {}
    llm_fast_model: str = ""  # 空则复用 llm_model

    # ── 服务 ──
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 2  # Gunicorn workers
    secret_key: str = ""  # JWT 签名密钥，必填

    # ── 安全 ──
    max_upload_size_mb: int = 100
    cors_origins: list[str] = ["*"]
    registration_open: bool = False

    # ── 保留策略 ──
    snapshot_retention_days: int = 30
    task_history_days: int = 7
    log_retention_days: int = 90

    # ── JWT ──
    access_token_expire_hours: int = 24
    refresh_token_expire_days: int = 7

    model_config = {
        "env_prefix": "LLM_WIKI_",
        "env_file": ".env",
        "extra": "ignore",
    }

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "Settings":
        """从 YAML 配置文件加载设置，优先级低于环境变量。"""
        import yaml

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        flat: dict[str, any] = {}
        if yaml_data and isinstance(yaml_data, dict):
            # 展平嵌套结构
            for section in ("llm", "service", "security", "retention"):
                section_data = yaml_data.get(section, {})
                if isinstance(section_data, dict):
                    for k, v in section_data.items():
                        flat[f"llm_{k}" if section == "llm" else k] = (
                            str(v) if not isinstance(v, (list, dict)) else v
                        )
            # 顶层简单字段
            for k in ("app_name", "debug", "log_level", "data_dir"):
                if k in yaml_data:
                    flat[k] = (
                        yaml_data[k]
                        if not isinstance(yaml_data[k], (list, dict))
                        else yaml_data[k]
                    )

        return cls(**flat)

    def validate_required(self):
        """启动时校验必填项，失败抛出 ConfigurationError。"""
        errors = []
        if not self.llm_api_key:
            errors.append(
                "LLM_WIKI_LLM_API_KEY 未设置。请设置环境变量或在 config.yaml 中配置。"
            )
        if not self.secret_key:
            errors.append(
                "LLM_WIKI_SECRET_KEY 未设置。请生成随机字符串：openssl rand -hex 32"
            )
        if errors:
            raise ConfigurationError("; ".join(errors))


class ConfigurationError(Exception):
    """配置错误异常。"""

    pass


# 全局单例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置单例。首次调用时从 config.yaml 加载。"""
    global _settings
    if _settings is None:
        yaml_path = Path("config.yaml")
        if yaml_path.exists():
            _settings = Settings.from_yaml(yaml_path)
        else:
            _settings = Settings()
    return _settings


def reset_settings():
    """重置全局配置（测试用）。"""
    global _settings
    _settings = None
