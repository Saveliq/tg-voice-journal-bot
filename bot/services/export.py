"""Генерация файлов экспорта всех записей пользователя (TXT/CSV/JSON)."""
from __future__ import annotations

import csv
import io
import json

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_all_entries
from bot.db.models import User

DATETIME_FMT = "%Y-%m-%d %H:%M"
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


async def export_txt(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    lines = [
        f"[{e.created_at.strftime(DATETIME_FMT)}] {e.content}" for e in entries
    ]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


async def export_csv(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "source_type", "content"])
    for e in entries:
        writer.writerow(
            [
                e.id,
                e.created_at.strftime(ISO_FMT),
                e.source_type.value,
                e.content,
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_json(session: AsyncSession, user: User) -> bytes:
    entries = await get_all_entries(session, user)
    data = [
        {
            "id": e.id,
            "created_at": e.created_at.strftime(ISO_FMT),
            "source_type": e.source_type.value,
            "content": e.content,
        }
        for e in entries
    ]
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


# fmt -> (функция, имя файла)
EXPORTERS = {
    "txt": (export_txt, "diary_export.txt"),
    "csv": (export_csv, "diary_export.csv"),
    "json": (export_json, "diary_export.json"),
}
