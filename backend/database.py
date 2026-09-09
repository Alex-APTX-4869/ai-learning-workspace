from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from backend.core.config import database_url


class Base(DeclarativeBase):
    """所有数据库模型共用的基类。"""


@lru_cache
def get_engine():
    # Engine（数据库引擎）管理连接；首次需要数据库时才创建。
    return create_engine(database_url(), pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    # 每次请求独立使用一个 Session（数据库会话），结束时自动关闭。
    with Session(get_engine()) as db:
        yield db
