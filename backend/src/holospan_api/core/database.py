from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from holospan_api.core.config import get_settings


class Base(DeclarativeBase):
    """Base for domain-owned PostgreSQL mappings."""


def create_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


engine = create_engine()
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
