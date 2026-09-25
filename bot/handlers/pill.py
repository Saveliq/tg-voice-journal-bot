"""Приём таблетки из главного меню или ежедневного напоминания."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.db import crud
from bot.db.session import async_session_factory
from bot.keyboards import CB_PILL_MENU, CB_PILL_TAKEN, feed_keyboard
from bot.services.feed import render_today_feed
from bot.services.pill import CONFIRM_TEXT
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.time_utils import local_today

logger = logging.getLogger(__name__)
router = Router(name="pill")

CONFIRM_DELETE_DELAY = 5  # секунд


async def _close_reminder(bot: Bot, chat_id: int, message_id: int) -> None:
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


@router.callback_query(F.data.in_({CB_PILL_MENU, CB_PILL_TAKEN}))
async def on_pill_taken(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    from_menu = callback.data == CB_PILL_MENU
    async with user_lock(callback.from_user.id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, callback.from_user.id)
            await crud.set_pill_taken_date(session, user, local_today(user))
            if not from_menu:
                await _close_reminder(bot, chat_id, message_id)
            # Как и после опроса о голове, возвращаемся к обычной ленте.
            await state.clear()
            text = await render_today_feed(session, user)
            await safe_edit_or_recreate(
                bot, session, user, text, feed_keyboard(user),
                prefer_message_id=message_id if from_menu else None,
            )
            sent = await bot.send_message(
                chat_id=chat_id, text=CONFIRM_TEXT, reply_markup=None,
            )

    # Не держим блокировку пользователя, пока показано подтверждение.
    await asyncio.sleep(CONFIRM_DELETE_DELAY)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
    except TelegramBadRequest as err:
        logger.debug("Не удалось удалить подтверждение %s: %s", sent.message_id, err)
