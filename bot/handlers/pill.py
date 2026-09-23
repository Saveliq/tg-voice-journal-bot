"""Подтверждение напоминания о таблетке без дополнительного опроса."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.keyboards import CB_PILL_TAKEN
from bot.services.pill import CONFIRM_TEXT
from bot.services.singleton_message import user_lock

logger = logging.getLogger(__name__)
router = Router(name="pill")


@router.callback_query(F.data == CB_PILL_TAKEN)
async def on_pill_taken(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer(CONFIRM_TEXT)
    if callback.message is None:
        return

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    async with user_lock(callback.from_user.id):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            # Старые сообщения Telegram может не разрешить удалить.
            try:
                await bot.edit_message_text(
                    text=CONFIRM_TEXT,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=None,
                )
            except TelegramBadRequest as err:
                logger.debug("Не удалось закрыть напоминание %s: %s", message_id, err)
