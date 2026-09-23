"""Режим одного дня (из календаря): просмотр + ввод информации задним числом.

Пока пользователь находится в этом режиме (FSM-состояние DayView.active),
любой текст/голос сохраняется заметкой на выбранный день, а не на сегодня.
Экран дня повторяет ленту, но с навигацией по дням и возвратом в обычный режим.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import crud
from bot.db.models import SourceType
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.keyboards import CB_DAY_NAV_PREFIX, day_view_keyboard
from bot.services.feed import render_day_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.sleep import maybe_record_sleep
from bot.services.time_utils import backdated_created_at
from bot.services.voice import transcribe_voice

logger = logging.getLogger(__name__)
router = Router(name="daymode")

VOICE_PROGRESS = "🎙 Распознаю голосовое..."
VOICE_FAILED = "⚠️ Не удалось распознать голосовое"
TRANSIENT_DELAY = 2.5


class DayView(StatesGroup):
    active = State()


async def enter_day_mode(
    bot: Bot,
    session,
    user,
    day: date,
    state: FSMContext,
    prefer_message_id: int | None = None,
) -> None:
    """Открыть/обновить экран дня и запомнить его в FSM."""
    await state.set_state(DayView.active)
    await state.update_data(day=day.isoformat())
    text = await render_day_feed(session, user, day)
    await safe_edit_or_recreate(
        bot, session, user, text, day_view_keyboard(day),
        prefer_message_id=prefer_message_id,
    )


async def _active_day(state: FSMContext) -> date | None:
    data = await state.get_data()
    iso = data.get("day")
    if not iso:
        return None
    try:
        return date.fromisoformat(iso)
    except ValueError:
        return None


async def _refresh_day(bot: Bot, session, user, day: date) -> None:
    text = await render_day_feed(session, user, day)
    await safe_edit_or_recreate(bot, session, user, text, day_view_keyboard(day))


@router.callback_query(DayView.active, F.data.startswith(CB_DAY_NAV_PREFIX))
async def on_day_nav(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # формат: day:nav:<ISO-date>
    iso = callback.data.split(":", 2)[2]
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        await callback.answer()
        return
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await enter_day_mode(bot, session, user, day, state)
    await callback.answer()


@router.message(DayView.active, F.text & ~F.text.startswith("/"))
async def on_day_text(message: Message, bot: Bot, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return
    tg_id = message.from_user.id
    content = message.text.strip()

    day = await _active_day(state)
    if day is None:
        await state.clear()
        return

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            if content:
                await crud.add_entry(
                    session, user, content, SourceType.text,
                    created_at=backdated_created_at(user, day),
                )
                await maybe_record_sleep(session, user, content, day=day)
            await delete_user_message(message)
            await _refresh_day(bot, session, user, day)


@router.message(DayView.active, F.voice)
async def on_day_voice(message: Message, bot: Bot, state: FSMContext) -> None:
    if message.from_user is None or message.voice is None:
        return
    tg_id = message.from_user.id
    file_id = message.voice.file_id

    day = await _active_day(state)
    if day is None:
        await state.clear()
        return

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)

            await safe_edit_or_recreate(
                bot, session, user, VOICE_PROGRESS, day_view_keyboard(day)
            )

            text = ""
            try:
                text = await transcribe_voice(bot, file_id)
            except Exception:  # noqa: BLE001
                logger.exception("Сбой транскрибации голосового (day) для user=%s", tg_id)

            await delete_user_message(message)

            if not text:
                await safe_edit_or_recreate(
                    bot, session, user, VOICE_FAILED, day_view_keyboard(day)
                )
                await asyncio.sleep(TRANSIENT_DELAY)
                await _refresh_day(bot, session, user, day)
                return

            await crud.add_entry(
                session, user, text, SourceType.voice,
                created_at=backdated_created_at(user, day),
            )
            await maybe_record_sleep(session, user, text, day=day)
            await _refresh_day(bot, session, user, day)


@router.message(DayView.active)
async def on_day_other(message: Message, bot: Bot, state: FSMContext) -> None:
    """Прочие типы сообщений в режиме дня — просто убрать и обновить экран."""
    if message.from_user is None:
        return
    tg_id = message.from_user.id
    day = await _active_day(state)
    if day is None:
        await state.clear()
        return
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await delete_user_message(message)
            await _refresh_day(bot, session, user, day)
