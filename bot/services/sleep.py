"""Обнаружение упоминаний сна в тексте и запись в дневник.

Логика: при первом упоминании сна за день автоматически добавляется
отдельная запись вида «сон X часов». Повторные упоминания в тот же день
игнорируются — фиксируется только первое.
"""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import crud
from bot.db.models import Entry, SourceType, User
from bot.services.time_utils import today_bounds_utc

# --- Паттерны извлечения часов ---

# "спал/поспал/проспал 8 часов" / "8,5 часов"
_PAT_EXPLICIT = re.compile(
    r'(?:по|про)?спал[аи]?\s+(\d+(?:[.,]\d+)?)\s*час',
    re.IGNORECASE,
)
# "сон 8 часов"
_PAT_NOUN = re.compile(
    r'\bсон\s+(\d+(?:[.,]\d+)?)\s*час',
    re.IGNORECASE,
)
# "8 часов сна"
_PAT_HOURS_OF = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*час\w*\s+сна',
    re.IGNORECASE,
)
# "спал с 23 до 7" / "с 23:30 до 7:00"
_PAT_RANGE = re.compile(
    r'(?:спал[аи]?\s+)?с\s+(\d{1,2})(?::(\d{2}))?\s+до\s+(\d{1,2})(?::(\d{2}))?',
    re.IGNORECASE,
)
# "лёг/лег в 23(:30), встал в 7(:30)"
_PAT_LAY_WAKE = re.compile(
    r'л[её]г\w*\s+в\s+(\d{1,2})(?::(\d{2}))?[^.!?]{0,40}?встал\w*\s+в\s+(\d{1,2})(?::(\d{2}))?',
    re.IGNORECASE,
)

# Маркер, по которому определяем уже сохранённую запись сна
_SLEEP_MARKER = "сон "


def _parse_hours(s: str) -> float:
    return float(s.replace(",", "."))


def _range_to_hours(h1: int, m1: int, h2: int, m2: int) -> float:
    start = h1 * 60 + m1
    end = h2 * 60 + m2
    if end <= start:          # пересечение полуночи
        end += 24 * 60
    return (end - start) / 60


def extract_sleep_hours(text: str) -> float | None:
    """Извлечь количество часов сна из произвольного текста.

    Возвращает float (может быть дробным) или None если упоминания нет.
    """
    for pat in (_PAT_EXPLICIT, _PAT_NOUN, _PAT_HOURS_OF):
        m = pat.search(text)
        if m:
            return _parse_hours(m.group(1))

    m = _PAT_RANGE.search(text)
    if m:
        h1, m1, h2, m2 = (
            int(m.group(1)), int(m.group(2) or 0),
            int(m.group(3)), int(m.group(4) or 0),
        )
        return _range_to_hours(h1, m1, h2, m2)

    m = _PAT_LAY_WAKE.search(text)
    if m:
        h1, m1, h2, m2 = (
            int(m.group(1)), int(m.group(2) or 0),
            int(m.group(3)), int(m.group(4) or 0),
        )
        return _range_to_hours(h1, m1, h2, m2)

    return None


def format_sleep_entry(hours: float) -> str:
    """'сон 8 часов' / 'сон 7,5 часов'."""
    if hours == int(hours):
        return f"сон {int(hours)} часов"
    return f"сон {hours:.1f} часов".replace(".", ",")


def _sleep_already_recorded(today_entries: list[Entry]) -> bool:
    return any(e.content.startswith(_SLEEP_MARKER) for e in today_entries)


async def maybe_record_sleep(
    session: AsyncSession, user: User, text: str
) -> bool:
    """Если в тексте есть упоминание сна и запись за сегодня ещё не добавлена —
    создать запись вида 'сон X часов'. Вернуть True если запись была создана.
    """
    hours = extract_sleep_hours(text)
    if hours is None or hours <= 0 or hours > 24:
        return False

    start, end = today_bounds_utc(user)
    today_entries = await crud.get_entries_between(session, user, start, end)
    if _sleep_already_recorded(today_entries):
        return False

    content = format_sleep_entry(hours)
    await crud.add_entry(session, user, content, SourceType.text)
    return True
