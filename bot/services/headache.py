"""Дневник головной боли: тексты, форматирование, отправка ежедневного промпта."""
from __future__ import annotations

import html
import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import crud
from bot.db.models import HeadacheEntry, User
from bot.keyboards import headache_ask_keyboard
from bot.services.time_utils import local_today

logger = logging.getLogger(__name__)

# Винительный падеж: «Начинаем запись на <день>»
_WEEKDAYS_ACC = (
    "понедельник", "вторник", "среду", "четверг",
    "пятницу", "субботу", "воскресенье",
)

PROMPT_TEXT = "Привет, это я!\nУ вас сегодня болела голова?"
PAINKILLER_TEXT = "Вы принимали обезболивающие? 💊"
MEDICATION_TEXT = "Какой препарат? В какой дозировке?"


def weekday_accusative(d: date) -> str:
    return _WEEKDAYS_ACC[d.weekday()]


def confirm_no_headache(d: date) -> str:
    return (
        "Готов!\n"
        f"Начинаем запись на {weekday_accusative(d)}\n"
        "Записал ответ\n"
        "Не болела 🙂"
    )


def confirm_headache(medication_name: str | None, took_painkiller: bool) -> str:
    lines = ["Записал: голова болела 🤕"]
    if took_painkiller and medication_name:
        lines.append(f"Препарат: {html.escape(medication_name)}")
    elif took_painkiller:
        lines.append("Обезболивающее принято")
    else:
        lines.append("Без обезболивающих")
    return "\n".join(lines)


def format_headache_feed_line(entry: HeadacheEntry, escape: bool = True) -> str:
    """Строка по одной записи ГБ.

    escape=True — для ленты (HTML parse mode), escape=False — для файлов экспорта.
    """
    if not entry.had_headache:
        return "🙂 Голова не болела"
    if entry.medication is not None:
        name = html.escape(entry.medication.name) if escape else entry.medication.name
        return f"🤕 Болела голова — {name}"
    if entry.took_painkiller:
        return "🤕 Болела голова — обезболивающее принято"
    return "🤕 Болела голова"


async def headache_lines_for_date(
    session: AsyncSession, user: User, entry_date: date
) -> list[str]:
    entries = await crud.get_headache_entries_for_date(session, user, entry_date)
    return [format_headache_feed_line(e) for e in entries]


def today_date(user: User) -> date:
    """Текущая локальная дата пользователя (его «сегодня»)."""
    return local_today(user)


async def send_daily_prompt(bot: Bot, session: AsyncSession, user: User) -> None:
    """Отправить пользователю ежедневный вопрос о головной боли за сегодня.

    Дата привязана к сообщению (локальное сегодня пользователя) — без выбора даты.
    """
    d = today_date(user)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=PROMPT_TEXT,
            reply_markup=headache_ask_keyboard(d),
        )
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — пропускаем.
        logger.info("Пользователь %s заблокировал бота, пропуск промпта", user.telegram_id)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить промпт ГБ user=%s", user.telegram_id)
