from collections.abc import AsyncIterator

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


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


settings = get_settings()
auth_engine = create_engine(settings.database_url)
tenant_engine = create_engine(settings.tenant_database_url)
auth_session_factory = async_sessionmaker(auth_engine, class_=AsyncSession, expire_on_commit=False)
tenant_session_factory = async_sessionmaker(
    tenant_engine, class_=AsyncSession, expire_on_commit=False
)


async def database_session() -> AsyncIterator[AsyncSession]:
    async with auth_session_factory() as session:
        yield session


async def tenant_database_session() -> AsyncIterator[AsyncSession]:
    async with tenant_session_factory() as session:
        yield session
