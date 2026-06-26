"""Catch-all хендлер: прочий ввод (другие команды, неподдержанные типы).

Чтобы в чате не оставалось следов ввода, любое необработанное сообщение
удаляется, а лента обновляется. Регистрируется ПОСЛЕДНИМ роутером.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import Message

from bot.db import crud
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.keyboards import feed_keyboard
from bot.services.feed import render_today_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock

logger = logging.getLogger(__name__)
router = Router(name="common")


@router.message()
async def on_other(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    tg_id = message.from_user.id

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await delete_user_message(message)
            text = await render_today_feed(session, user)
            await safe_edit_or_recreate(bot, session, user, text, feed_keyboard())
