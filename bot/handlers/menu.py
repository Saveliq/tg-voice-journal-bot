"""Callback-хендлеры меню: статистика, экспорт, навигация."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.db import crud
from bot.db.session import async_session_factory
from bot.keyboards import (
    CB_EXPORT,
    CB_EXPORT_CSV,
    CB_EXPORT_JSON,
    CB_EXPORT_TXT,
    CB_FEED,
    CB_STATS,
    export_keyboard,
    feed_keyboard,
    stats_keyboard,
)
from bot.services import export as export_service
from bot.services.feed import render_today_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.stats import render_stats

logger = logging.getLogger(__name__)
router = Router(name="menu")

_EXPORT_DELETE_DELAY = 30  # секунд


async def _delete_after(bot: Bot, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(_EXPORT_DELETE_DELAY)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


def _clicked_message_id(callback: CallbackQuery) -> int | None:
    """id сообщения, на котором нажата кнопка (заведомо «живое» сообщение)."""
    return callback.message.message_id if callback.message else None


@router.callback_query(F.data == CB_FEED)
async def on_feed(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            text = await render_today_feed(session, user)
            await safe_edit_or_recreate(
                bot, session, user, text, feed_keyboard(),
                prefer_message_id=_clicked_message_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data == CB_STATS)
async def on_stats(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            text = await render_stats(session, user)
            await safe_edit_or_recreate(
                bot, session, user, text, stats_keyboard(),
                prefer_message_id=_clicked_message_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data == CB_EXPORT)
async def on_export_menu(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    text = "<b>📤 Экспорт</b>\n\nВыбери формат — пришлю файл со всей историей записей."
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await safe_edit_or_recreate(
                bot, session, user, text, export_keyboard(),
                prefer_message_id=_clicked_message_id(callback),
            )
    await callback.answer()


_FORMAT_BY_CB = {
    CB_EXPORT_TXT: "txt",
    CB_EXPORT_CSV: "csv",
    CB_EXPORT_JSON: "json",
}


@router.callback_query(F.data.in_(_FORMAT_BY_CB.keys()))
async def on_export_format(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    fmt = _FORMAT_BY_CB[callback.data]
    exporter, filename = export_service.EXPORTERS[fmt]

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            payload = await exporter(session, user)

    if not payload:
        await callback.answer("Записей пока нет", show_alert=True)
        return

    sent = await bot.send_document(
        chat_id=tg_id,
        document=BufferedInputFile(payload, filename=filename),
        caption=f"Экспорт ({fmt.upper()}) — удалится через {_EXPORT_DELETE_DELAY} сек",
    )
    asyncio.create_task(_delete_after(bot, tg_id, sent.message_id))
    await callback.answer("Готово ✅")
