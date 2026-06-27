"""Генерация файлов экспорта всех записей пользователя (TXT/CSV/JSON)."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_all_entries
from bot.db.models import Entry, User

ISO_FMT = "%Y-%m-%dT%H:%M:%S"

_WEEKDAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")

_SLEEP_MARKER = "сон "


def _day_header(d: date) -> str:
    day_name = _WEEKDAYS_RU[d.weekday()]
    month_name = _MONTHS_RU[d.month - 1]
    return f"{day_name}, {d.day} {month_name} {d.year}"


def _group_by_day(entries: list[Entry]) -> list[tuple[date, list[Entry]]]:
    groups: dict[date, list[Entry]] = defaultdict(list)
    for e in entries:
        groups[e.created_at.date()].append(e)
    return sorted(groups.items())


def _split_sleep(day_entries: list[Entry]) -> tuple[str | None, list[str]]:
    """Вернуть (запись_сна | None, [остальные тексты]) — как в ленте бота."""
    sleep: str | None = None
    rest: list[str] = []
    for e in day_entries:
        content = e.content.strip()
        if sleep is None and content.lower().startswith(_SLEEP_MARKER):
            sleep = content
        else:
            rest.append(content)
    return sleep, rest


def _day_block(day: date, day_entries: list[Entry]) -> str:
    """Один блок дня в том же формате, что лента бота."""
    header = _day_header(day)
    sleep, rest = _split_sleep(day_entries)

    parts: list[str] = []
    if sleep:
        parts.append(sleep)
    if rest:
        parts.append(". ".join(rest))

    body = "\n\n".join(parts) if parts else ""
    return f"{header}\n\n{body}" if body else header


async def export_txt(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    if not entries:
        return b""

    blocks = [_day_block(day, day_entries) for day, day_entries in _group_by_day(entries)]
    return ("\n\n---\n\n".join(blocks) + "\n").encode("utf-8")


async def export_csv(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "source_type", "content"])
    for e in entries:
        writer.writerow([
            e.created_at.strftime(ISO_FMT),
            e.source_type.value,
            e.content,
        ])
    return buf.getvalue().encode("utf-8")


async def export_json(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    data: list[dict] = []
    for day, day_entries in _group_by_day(entries):
        sleep, rest = _split_sleep(day_entries)
        data.append({
            "date": day.isoformat(),
            "header": _day_header(day),
            "sleep": sleep,
            "entries": rest,
        })
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


# fmt -> (функция, имя файла)
EXPORTERS = {
    "txt": (export_txt, "diary_export.txt"),
    "csv": (export_csv, "diary_export.csv"),
    "json": (export_json, "diary_export.json"),
}
