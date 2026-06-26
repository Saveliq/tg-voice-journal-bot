"""Подсчёт и форматирование статистики."""
from __future__ import annotations

import html
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import (
    count_entries,
    count_entries_between,
    get_all_entries,
)
from bot.db.models import User
from bot.services.time_utils import day_bounds, today_bounds

DAYS_WINDOW = 7


async def render_stats(session: AsyncSession, user: User) -> str:
    """Сформировать текст раздела статистики."""
    total = await count_entries(session, user)

    start_today, end_today = today_bounds()
    today_count = await count_entries_between(session, user, start_today, end_today)

    lines = [
        "<b>📊 Статистика</b>",
        "",
        f"Всего записей: <b>{total}</b>",
        f"Сегодня: <b>{today_count}</b>",
        "",
        f"<b>Последние {DAYS_WINDOW} дней:</b>",
    ]

    today_date = start_today.date()
    for i in range(DAYS_WINDOW):
        day = today_date - timedelta(days=i)
        d_start, d_end = day_bounds(day)
        cnt = await count_entries_between(session, user, d_start, d_end)
        lines.append(f"{day.isoformat()}: {cnt} записей")

    return "\n".join(html.escape(line) if "<" not in line else line for line in lines)


async def has_any_entries(session: AsyncSession, user: User) -> bool:
    entries = await get_all_entries(session, user)
    return bool(entries)
