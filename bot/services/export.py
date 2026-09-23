"""Генерация файлов экспорта всех записей пользователя (TXT/CSV/JSON)."""
from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_all_entries, get_all_headache_entries
from bot.db.models import Entry, HeadacheEntry, User
from bot.services.headache import format_headache_feed_line

ISO_FMT = "%Y-%m-%dT%H:%M:%S"

_WEEKDAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")

_SLEEP_MARKER = "сон "
# Ведущее «сон N часов» в тексте записи — дублирует отдельную строку сна.
_SLEEP_DUP_RE = re.compile(r'^\s*сон\s+\d+(?:[.,]\d+)?\s*час\w*', re.IGNORECASE)


def _strip_sleep_dup(text: str) -> str:
    """Убрать ведущее «сон N часов» из записи (оно уже показано отдельной строкой)."""
    m = _SLEEP_DUP_RE.match(text)
    if not m:
        return text
    return text[m.end():].lstrip(" .,;:—-\n\t")


def _visible_headache(entries: list[HeadacheEntry]) -> list[HeadacheEntry]:
    """Только записи, где голова болела — «не болела» в экспорт не попадает."""
    return [e for e in entries if e.had_headache]


def _day_header(d: date) -> str:
    day_name = _WEEKDAYS_RU[d.weekday()]
    month_name = _MONTHS_RU[d.month - 1]
    return f"{day_name}, {d.day} {month_name} {d.year}"


def _group_by_day(entries: list[Entry]) -> dict[date, list[Entry]]:
    groups: dict[date, list[Entry]] = defaultdict(list)
    for e in entries:
        groups[e.created_at.date()].append(e)
    return groups


def _group_headache_by_day(
    entries: list[HeadacheEntry],
) -> dict[date, list[HeadacheEntry]]:
    groups: dict[date, list[HeadacheEntry]] = defaultdict(list)
    for e in entries:
        groups[e.entry_date].append(e)
    return groups


def _split_sleep(day_entries: list[Entry]) -> tuple[str | None, list[str]]:
    """Вернуть (запись_сна | None, [остальные тексты]) — как в ленте бота.

    Если строка сна выделена отдельно, из остальных записей убирается
    дублирующее ведущее «сон N часов» (напр. «сон 12 часов. Хочется спать»
    → «Хочется спать»); полностью дублирующие записи отбрасываются.
    """
    sleep: str | None = None
    rest: list[str] = []
    for e in day_entries:
        content = e.content.strip()
        if sleep is None and content.lower().startswith(_SLEEP_MARKER):
            sleep = content
        else:
            rest.append(content)
    if sleep is not None:
        rest = [r for r in (_strip_sleep_dup(x) for x in rest) if r]
    return sleep, rest


def _day_block(
    day: date, day_entries: list[Entry], hd_entries: list[HeadacheEntry]
) -> str:
    """Один блок дня в том же формате, что лента бота."""
    header = _day_header(day)
    sleep, rest = _split_sleep(day_entries)
    hd_lines = [format_headache_feed_line(e, escape=False) for e in hd_entries]

    top = ([sleep] if sleep else []) + hd_lines

    parts: list[str] = []
    if top:
        parts.append("\n".join(top))
    if rest:
        parts.append(". ".join(rest))

    body = "\n\n".join(parts) if parts else ""
    return f"{header}\n\n{body}" if body else header


async def export_txt(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    hd_entries = _visible_headache(await get_all_headache_entries(session, user))
    if not entries and not hd_entries:
        return b""

    by_day = _group_by_day(entries)
    hd_by_day = _group_headache_by_day(hd_entries)
    all_days = sorted(set(by_day) | set(hd_by_day))

    blocks = [
        _day_block(day, by_day.get(day, []), hd_by_day.get(day, []))
        for day in all_days
    ]
    return ("\n\n---\n\n".join(blocks) + "\n").encode("utf-8")


async def export_csv(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    hd_entries = _visible_headache(await get_all_headache_entries(session, user))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "source_type", "content"])
    for e in entries:
        writer.writerow([
            e.created_at.strftime(ISO_FMT),
            e.source_type.value,
            e.content,
        ])
    for e in hd_entries:
        writer.writerow([
            e.entry_date.isoformat(),
            "headache",
            format_headache_feed_line(e, escape=False),
        ])
    return buf.getvalue().encode("utf-8")


async def export_json(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    hd_entries = _visible_headache(await get_all_headache_entries(session, user))

    by_day = _group_by_day(entries)
    hd_by_day = _group_headache_by_day(hd_entries)
    all_days = sorted(set(by_day) | set(hd_by_day))

    data: list[dict] = []
    for day in all_days:
        sleep, rest = _split_sleep(by_day.get(day, []))
        hd_lines = [
            format_headache_feed_line(e, escape=False)
            for e in hd_by_day.get(day, [])
        ]
        data.append({
            "date": day.isoformat(),
            "header": _day_header(day),
            "sleep": sleep,
            "headache": hd_lines,
            "entries": rest,
        })
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


# fmt -> (функция, имя файла)
EXPORTERS = {
    "txt": (export_txt, "diary_export.txt"),
    "csv": (export_csv, "diary_export.csv"),
    "json": (export_json, "diary_export.json"),
}
