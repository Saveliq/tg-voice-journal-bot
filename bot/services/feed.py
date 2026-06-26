"""Формирование текста ленты за сегодня с учётом лимита Telegram."""
from __future__ import annotations

import html

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_entries_between
from bot.db.models import Entry, User
from bot.services.time_utils import today_bounds

# Лимит Telegram на текст сообщения — 4096 символов. Берём с запасом.
TG_MESSAGE_LIMIT = 4096
SAFE_LIMIT = 3900

HEADER = "<b>📔 Дневник — сегодня</b>"
EMPTY_HINT = (
    "Сегодня записей пока нет.\n"
    "Просто напиши текст или отправь голосовое."
)
TRUNCATED_NOTE = "\n<i>…показаны последние записи, остальные доступны через экспорт</i>"


def format_entry(entry: Entry) -> str:
    """Одна строка ленты: '🕐 14:32  текст'."""
    t = entry.created_at.strftime("%H:%M")
    content = html.escape(entry.content.strip())
    return f"🕐 {t}  {content}"


def build_feed_text(entries: list[Entry]) -> str:
    """Собрать текст ленты, обрезая с начала, если не влезает в лимит."""
    if not entries:
        return f"{HEADER}\n\n{EMPTY_HINT}"

    lines = [format_entry(e) for e in entries]
    body = "\n".join(lines)
    text = f"{HEADER}\n\n{body}"

    if len(text) <= SAFE_LIMIT:
        return text

    # Не влезает — оставляем только последние записи + пометку об обрезке.
    truncated: list[str] = []
    running = len(HEADER) + 2 + len(TRUNCATED_NOTE)
    for line in reversed(lines):
        addition = len(line) + 1
        if running + addition > SAFE_LIMIT:
            break
        truncated.append(line)
        running += addition
    truncated.reverse()
    body = "\n".join(truncated)
    return f"{HEADER}\n\n{body}{TRUNCATED_NOTE}"


async def render_today_feed(session: AsyncSession, user: User) -> str:
    """Загрузить записи за сегодня и отдать готовый текст ленты."""
    start, end = today_bounds()
    entries = await get_entries_between(session, user, start, end)
    return build_feed_text(entries)
