"""Функции доступа к данным: пользователи и записи."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry, SourceType, User


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    """Найти пользователя по telegram_id или создать нового."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def set_pinned_message_id(
    session: AsyncSession, user: User, message_id: int | None
) -> None:
    user.pinned_message_id = message_id
    session.add(user)
    await session.commit()


async def add_entry(
    session: AsyncSession,
    user: User,
    content: str,
    source_type: SourceType,
) -> Entry:
    entry = Entry(user_id=user.id, content=content, source_type=source_type)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_entries_between(
    session: AsyncSession, user: User, start: datetime, end: datetime
) -> list[Entry]:
    """Записи пользователя в интервале [start, end), отсортированы по времени."""
    result = await session.execute(
        select(Entry)
        .where(
            Entry.user_id == user.id,
            Entry.created_at >= start,
            Entry.created_at < end,
        )
        .order_by(Entry.created_at.asc())
    )
    return list(result.scalars().all())


async def get_all_entries(session: AsyncSession, user: User) -> list[Entry]:
    result = await session.execute(
        select(Entry)
        .where(Entry.user_id == user.id)
        .order_by(Entry.created_at.asc())
    )
    return list(result.scalars().all())


async def count_entries(session: AsyncSession, user: User) -> int:
    result = await session.execute(
        select(func.count(Entry.id)).where(Entry.user_id == user.id)
    )
    return int(result.scalar_one())


async def count_entries_between(
    session: AsyncSession, user: User, start: datetime, end: datetime
) -> int:
    result = await session.execute(
        select(func.count(Entry.id)).where(
            Entry.user_id == user.id,
            Entry.created_at >= start,
            Entry.created_at < end,
        )
    )
    return int(result.scalar_one())
