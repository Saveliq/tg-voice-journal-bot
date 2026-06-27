"""Async engine и фабрика сессий SQLAlchemy."""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.db.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# Колонки, которые могли отсутствовать в ранее созданной таблице users.
# create_all не изменяет существующие таблицы, поэтому добавляем их вручную.
# (name, SQL-тип, SQL-выражение DEFAULT)
_USER_COLUMNS_MIGRATION = [
    ("prompt_time", "VARCHAR(5)", "'20:00'"),
    ("prompt_enabled", "BOOLEAN", None),  # default зависит от диалекта, см. ниже
]


def _ensure_user_columns(conn) -> None:
    """Лёгкая идемпотентная миграция: добавить недостающие колонки в users.

    Запускается синхронно внутри run_sync. Работает на SQLite и PostgreSQL.
    """
    insp = inspect(conn)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    is_pg = conn.dialect.name == "postgresql"
    bool_true = "TRUE" if is_pg else "1"

    for name, sql_type, default in _USER_COLUMNS_MIGRATION:
        if name in existing:
            continue
        if name == "prompt_enabled":
            default = bool_true
        ddl = f"ALTER TABLE users ADD COLUMN {name} {sql_type} DEFAULT {default}"
        logger.info("Миграция users: %s", ddl)
        conn.execute(text(ddl))


async def init_db() -> None:
    """Создать таблицы и применить лёгкие миграции.

    Для prod рекомендуется alembic; здесь create_all + ручной ALTER удобны для
    SQLite-dev и для добавления колонок в уже существующую prod-таблицу.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_user_columns)
