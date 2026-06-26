"""Хендлер /start — инициализация пользователя и первой ленты."""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db import crud
from bot.db.session import async_session_factory
from bot.keyboards import feed_keyboard
from bot.services.feed import render_today_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock

logger = logging.getLogger(__name__)
router = Router(name="start")


async def delete_user_message(message: Message) -> None:
    """Удалить входящее сообщение пользователя (best-effort)."""
    try:
        await message.delete()
    except TelegramBadRequest as err:
        logger.debug("Не удалось удалить сообщение пользователя: %s", err)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    tg_id = message.from_user.id

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            text = await render_today_feed(session, user)
            await safe_edit_or_recreate(
                bot, session, user, text, feed_keyboard()
            )

    await delete_user_message(message)
