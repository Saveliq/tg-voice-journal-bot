"""Формирование текста ленты за сегодня с учётом лимита Telegram."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_entries_between
from bot.db.models import Entry, User
from bot.services.time_utils import today_bounds

# Лимит Telegram на текст сообщения — 4096 символов. Берём с запасом.
TG_MESSAGE_LIMIT = 4096
SAFE_LIMIT = 3900

EMPTY_HINT = "Просто напиши текст или отправь голосовое."
TRUNCATED_NOTE = " <i>…часть записей скрыта, доступна через экспорт</i>"

_WEEKDAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")


def _today_header() -> str:
    now = datetime.now(timezone.utc)
    day_name = _WEEKDAYS_RU[now.weekday()]
    month_name = _MONTHS_RU[now.month - 1]
    return f"<b>{day_name}, {now.day} {month_name}</b>"


_SLEEP_MARKER = "сон "


def _split_entries(entries: list[Entry]) -> tuple[str | None, list[str]]:
    """Разделить записи на запись сна и остальные.

    Возвращает (sleep_line | None, [остальные строки]).
    """
    sleep_line: str | None = None
    rest: list[str] = []
    for e in entries:
        content = html.escape(e.content.strip())
        if sleep_line is None and e.content.strip().lower().startswith(_SLEEP_MARKER):
            sleep_line = content
        else:
            rest.append(content)
    return sleep_line, rest


def build_feed_text(entries: list[Entry]) -> str:
    """Собрать текст ленты.

    Структура:
        <дата>

        сон X часов        ← если есть, всегда сразу после даты
        (пустая строка)
        запись1. запись2.  ← остальные через '. '
    """
    header = _today_header()

    if not entries:
        return f"{header}\n\n{EMPTY_HINT}"

    sleep_line, rest_parts = _split_entries(entries)

    # Собираем полный текст для проверки лимита
    body_parts: list[str] = []
    if sleep_line:
        body_parts.append(sleep_line)
    if rest_parts:
        body_parts.append(". ".join(rest_parts))

    body = "\n\n".join(body_parts) if body_parts else EMPTY_HINT
    text = f"{header}\n\n{body}"

    if len(text) <= SAFE_LIMIT:
        return text

    # Не влезает — обрезаем rest с конца, сон сохраняем всегда.
    truncated: list[str] = []
    overhead = len(header) + 2 + (len(sleep_line) + 2 if sleep_line else 0) + len(TRUNCATED_NOTE)
    running = overhead
    for part in reversed(rest_parts):
        addition = len(part) + 2
        if running + addition > SAFE_LIMIT:
            break
        truncated.append(part)
        running += addition
    truncated.reverse()

    body_parts = []
    if sleep_line:
        body_parts.append(sleep_line)
    if truncated:
        body_parts.append(". ".join(truncated) + TRUNCATED_NOTE)
    elif not sleep_line:
        body_parts.append(EMPTY_HINT)

    return f"{header}\n\n" + "\n\n".join(body_parts)


async def render_today_feed(session: AsyncSession, user: User) -> str:
    """Загрузить записи за сегодня и отдать готовый текст ленты."""
    start, end = today_bounds()
    entries = await get_entries_between(session, user, start, end)
    return build_feed_text(entries)
