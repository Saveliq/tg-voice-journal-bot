"""Хендлеры календаря головной боли.

Два режима (визуально идентичны):
- view (📅 Календарь из меню): тап по дате → popup с записями дня;
- pick (📅 Календарь из выбора даты): тап по дате → начать запись (hd:pick).
"""
from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.db import crud
from bot.db.session import async_session_factory
from bot.handlers.daymode import enter_day_mode
from bot.keyboards import (
    CAL_MODE_PICK,
    CAL_MODE_VIEW,
    CB_CAL_NOOP,
    CB_CAL_PICKOPEN,
    CB_CALENDAR,
    calendar_keyboard,
)
from bot.services import calendar_view as cv
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.time_utils import local_today

logger = logging.getLogger(__name__)
router = Router(name="calendar")


def _clicked_id(callback: CallbackQuery) -> int | None:
    return callback.message.message_id if callback.message else None


async def _render(
    bot: Bot,
    callback: CallbackQuery,
    year: int | None,
    month: int | None,
    mode: str,
    state: FSMContext,
) -> None:
    # Показ сетки календаря — выход из режима одного дня, если он был активен.
    await state.clear()
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            if year is None or month is None:
                today = local_today(user)
                year, month = today.year, today.month
            first, last = cv.month_range(year, month)
            entries = await crud.get_headache_entries_between_dates(
                session, user, first, last
            )
            text = cv.month_stats_text(year, month, entries)
            symbols = cv.day_symbols(entries)
            await safe_edit_or_recreate(
                bot, session, user, text,
                calendar_keyboard(year, month, symbols, mode=mode),
                prefer_message_id=_clicked_id(callback),
            )


@router.callback_query(F.data == CB_CALENDAR)
async def on_open_view(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await _render(bot, callback, None, None, CAL_MODE_VIEW, state)
    await callback.answer()


@router.callback_query(F.data == CB_CAL_PICKOPEN)
async def on_open_pick(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await _render(bot, callback, None, None, CAL_MODE_PICK, state)
    await callback.answer()


@router.callback_query(F.data.startswith("cal:nav:"))
async def on_nav(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # формат: cal:nav:<mode>:<YYYY-MM>
    _, _, mode, ym = callback.data.split(":", 3)
    try:
        year, month = (int(x) for x in ym.split("-", 1))
    except ValueError:
        year = month = None
    await _render(bot, callback, year, month, mode, state)
    await callback.answer()


@router.callback_query(F.data.startswith("cal:day:"))
async def on_day(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # формат: cal:day:<ISO-date> — открыть экран дня (просмотр + ввод на этот день)
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
            await enter_day_mode(
                bot, session, user, day, state,
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data == CB_CAL_NOOP)
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()
