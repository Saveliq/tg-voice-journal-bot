"""Async engine и фабрика сессий SQLAlchemy."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.db.models import Base

engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Создать таблицы на этапе разработки (вместо alembic upgrade).

    Для prod рекомендуется alembic; здесь create_all удобен для SQLite-dev.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
