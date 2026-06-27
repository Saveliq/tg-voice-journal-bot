"""Формирование текста ленты за сегодня с учётом лимита Telegram."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_entries_between, get_headache_entries_for_date
from bot.db.models import Entry, User
from bot.services.headache import format_headache_feed_line
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


def build_feed_text(
    entries: list[Entry], headache_lines: list[str] | None = None
) -> str:
    """Собрать текст ленты.

    Структура:
        <дата>

        сон X часов          ← если есть, сразу после даты
        🤕 Болела голова …   ← записи дневника ГБ (каждая на своей строке)
        (пустая строка)
        запись1. запись2.    ← текст/голос через '. '
    """
    header = _today_header()
    headache_lines = headache_lines or []

    sleep_line, rest_parts = _split_entries(entries)

    if not entries and not headache_lines:
        return f"{header}\n\n{EMPTY_HINT}"

    # «Верхний» блок: сон + строки головной боли (каждая со своей строки)
    top_lines: list[str] = []
    if sleep_line:
        top_lines.append(sleep_line)
    # headache_lines уже безопасный HTML (см. format_headache_feed_line)
    top_lines.extend(headache_lines)

    body_parts: list[str] = []
    if top_lines:
        body_parts.append("\n".join(top_lines))
    if rest_parts:
        body_parts.append(". ".join(rest_parts))

    body = "\n\n".join(body_parts) if body_parts else EMPTY_HINT
    text = f"{header}\n\n{body}"

    if len(text) <= SAFE_LIMIT:
        return text

    # Не влезает — обрезаем текстовые записи с конца, верхний блок сохраняем.
    top_block = "\n".join(top_lines)
    overhead = len(header) + 2 + (len(top_block) + 2 if top_block else 0) + len(TRUNCATED_NOTE)
    truncated: list[str] = []
    running = overhead
    for part in reversed(rest_parts):
        addition = len(part) + 2
        if running + addition > SAFE_LIMIT:
            break
        truncated.append(part)
        running += addition
    truncated.reverse()

    body_parts = []
    if top_block:
        body_parts.append(top_block)
    if truncated:
        body_parts.append(". ".join(truncated) + TRUNCATED_NOTE)
    elif not top_block:
        body_parts.append(EMPTY_HINT)

    return f"{header}\n\n" + "\n\n".join(body_parts)


async def render_today_feed(session: AsyncSession, user: User) -> str:
    """Загрузить записи за сегодня (текст/голос + ГБ) и отдать текст ленты."""
    start, end = today_bounds()
    entries = await get_entries_between(session, user, start, end)

    hd_entries = await get_headache_entries_for_date(session, user, start.date())
    headache_lines = [format_headache_feed_line(e) for e in hd_entries]

    return build_feed_text(entries, headache_lines)
