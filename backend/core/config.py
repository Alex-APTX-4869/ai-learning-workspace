import os
from pathlib import Path

from dotenv import load_dotenv

# 明确定位项目根目录，不依赖终端当前在哪个文件夹。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"请在项目根目录 .env 中配置 {name}")
    return value


def database_url() -> str:
    return required_env("DATABASE_URL")


def nus_settings() -> tuple[str, str, str]:
    return required_env("NUS_API_KEY"), required_env("NUS_URL"), required_env("NUS_MODEL")
