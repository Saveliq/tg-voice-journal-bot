"""Хендлеры записей: текст и голосовые сообщения."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.db import crud
from bot.db.models import SourceType
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.keyboards import feed_keyboard
from bot.services.feed import render_today_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.sleep import maybe_record_sleep
from bot.services.voice import transcribe_voice

logger = logging.getLogger(__name__)
router = Router(name="entries")

VOICE_PROGRESS = "🎙 Распознаю голосовое..."
VOICE_FAILED = "⚠️ Не удалось распознать голосовое"
TRANSIENT_DELAY = 2.5  # сек — показ коротких уведомлений


async def _refresh_feed(bot: Bot, session, user) -> None:
    text = await render_today_feed(session, user)
    await safe_edit_or_recreate(bot, session, user, text, feed_keyboard())


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot) -> None:
    if message.from_user is None or message.text is None:
        return
    tg_id = message.from_user.id
    content = message.text.strip()

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            if content:
                await crud.add_entry(session, user, content, SourceType.text)
                await maybe_record_sleep(session, user, content)
            # Удаляем ввод только после сохранения записи.
            await delete_user_message(message)
            await _refresh_feed(bot, session, user)


@router.message(F.voice)
async def on_voice(message: Message, bot: Bot) -> None:
    if message.from_user is None or message.voice is None:
        return
    tg_id = message.from_user.id
    file_id = message.voice.file_id

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)

            # Промежуточный статус, чтобы бот не выглядел зависшим.
            await safe_edit_or_recreate(
                bot, session, user, VOICE_PROGRESS, feed_keyboard()
            )

            text = ""
            try:
                text = await transcribe_voice(bot, file_id)
            except Exception:  # noqa: BLE001 — логируем любой сбой транскрибации
                logger.exception("Сбой транскрибации голосового для user=%s", tg_id)

            # Контент извлечён — теперь можно удалить входящее сообщение.
            await delete_user_message(message)

            if not text:
                # Короткое уведомление, затем возврат ленты.
                await safe_edit_or_recreate(
                    bot, session, user, VOICE_FAILED, feed_keyboard()
                )
                await asyncio.sleep(TRANSIENT_DELAY)
                await _refresh_feed(bot, session, user)
                return

            await crud.add_entry(session, user, text, SourceType.voice)
            await maybe_record_sleep(session, user, text)
            await _refresh_feed(bot, session, user)
