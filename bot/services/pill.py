"""Ежедневное напоминание о приёме таблетки."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from bot.db.models import User
from bot.keyboards import pill_ask_keyboard
from bot.services.time_utils import local_today

logger = logging.getLogger(__name__)

PROMPT_TEXT = "выпил таблетку ?"
CONFIRM_TEXT = "Таблетка принята ✅"


async def send_daily_prompt(bot: Bot, user: User) -> None:
    if user.pill_taken_date == local_today(user):
        return

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=PROMPT_TEXT,
            reply_markup=pill_ask_keyboard(),
        )
    except TelegramForbiddenError:
        logger.info("Пользователь %s заблокировал бота, пропуск таблетки", user.telegram_id)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить напоминание о таблетке user=%s", user.telegram_id)
