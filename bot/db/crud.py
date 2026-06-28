"""Функции доступа к данным: пользователи и записи."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.db.models import (
    Entry,
    HeadacheEntry,
    Medication,
    SourceType,
    User,
)


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    """Найти пользователя по telegram_id или создать нового."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            prompt_time=settings.headache_prompt_time,
            timezone=settings.default_tz,
        )
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


# --- Пользователи (для рассылки) ---

async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars().all())


async def get_enabled_users(session: AsyncSession) -> list[User]:
    """Пользователи с включённым ежедневным напоминанием."""
    result = await session.execute(
        select(User).where(User.prompt_enabled.is_(True))
    )
    return list(result.scalars().all())


async def set_timezone(session: AsyncSession, user: User, tz_name: str) -> None:
    user.timezone = tz_name
    session.add(user)
    await session.commit()


async def set_prompt_time(session: AsyncSession, user: User, hh_mm: str) -> None:
    user.prompt_time = hh_mm
    session.add(user)
    await session.commit()


async def set_prompt_enabled(
    session: AsyncSession, user: User, enabled: bool
) -> None:
    user.prompt_enabled = enabled
    session.add(user)
    await session.commit()


# --- Препараты ---

async def get_or_create_medication(
    session: AsyncSession, user: User, name: str
) -> Medication:
    name = name.strip()
    result = await session.execute(
        select(Medication).where(
            Medication.user_id == user.id, Medication.name == name
        )
    )
    med = result.scalar_one_or_none()
    if med is None:
        med = Medication(user_id=user.id, name=name)
        session.add(med)
        await session.commit()
        await session.refresh(med)
    return med


async def get_medication(session: AsyncSession, med_id: int) -> Medication | None:
    return await session.get(Medication, med_id)


async def list_medications(
    session: AsyncSession, user: User, limit: int = 8
) -> list[Medication]:
    """Недавно использованные препараты пользователя (по убыванию свежести)."""
    result = await session.execute(
        select(Medication)
        .where(Medication.user_id == user.id)
        .order_by(Medication.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# --- Записи головной боли ---

async def create_headache_entry(
    session: AsyncSession,
    user: User,
    entry_date: date,
    had_headache: bool,
) -> HeadacheEntry:
    entry = HeadacheEntry(
        user_id=user.id, entry_date=entry_date, had_headache=had_headache
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_headache_entry(
    session: AsyncSession, entry_id: int
) -> HeadacheEntry | None:
    return await session.get(HeadacheEntry, entry_id)


async def update_headache_entry(
    session: AsyncSession,
    entry: HeadacheEntry,
    *,
    took_painkiller: bool | None = None,
    medication_id: int | None = None,
) -> None:
    if took_painkiller is not None:
        entry.took_painkiller = took_painkiller
    if medication_id is not None:
        entry.medication_id = medication_id
    session.add(entry)
    await session.commit()


async def get_headache_entries_for_date(
    session: AsyncSession, user: User, entry_date: date
) -> list[HeadacheEntry]:
    result = await session.execute(
        select(HeadacheEntry)
        .where(
            HeadacheEntry.user_id == user.id,
            HeadacheEntry.entry_date == entry_date,
        )
        .order_by(HeadacheEntry.created_at.asc())
    )
    return list(result.scalars().all())


async def get_all_headache_entries(
    session: AsyncSession, user: User
) -> list[HeadacheEntry]:
    result = await session.execute(
        select(HeadacheEntry)
        .where(HeadacheEntry.user_id == user.id)
        .order_by(HeadacheEntry.entry_date.asc(), HeadacheEntry.created_at.asc())
    )
    return list(result.scalars().all())


async def get_headache_entries_between_dates(
    session: AsyncSession, user: User, first: date, last: date
) -> list[HeadacheEntry]:
    """Записи ГБ в диапазоне дат [first, last] включительно (для календаря)."""
    result = await session.execute(
        select(HeadacheEntry)
        .where(
            HeadacheEntry.user_id == user.id,
            HeadacheEntry.entry_date >= first,
            HeadacheEntry.entry_date <= last,
        )
        .order_by(HeadacheEntry.entry_date.asc(), HeadacheEntry.created_at.asc())
    )
    return list(result.scalars().all())
