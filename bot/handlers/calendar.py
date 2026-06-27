"""Хендлеры календаря головной боли: открытие, навигация по месяцам, тап по дате."""
from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from bot.db import crud
from bot.db.session import async_session_factory
from bot.keyboards import CB_CALENDAR, CB_CAL_NOOP, calendar_keyboard
from bot.services import calendar_view as cv
from bot.services.headache import today_date
from bot.services.singleton_message import safe_edit_or_recreate, user_lock

logger = logging.getLogger(__name__)
router = Router(name="calendar")


def _clicked_id(callback: CallbackQuery) -> int | None:
    return callback.message.message_id if callback.message else None


async def _render(bot: Bot, callback: CallbackQuery, year: int, month: int) -> None:
    tg_id = callback.from_user.id
    first, last = cv.month_range(year, month)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            entries = await crud.get_headache_entries_between_dates(
                session, user, first, last
            )
            text = cv.month_stats_text(year, month, entries)
            symbols = cv.day_symbols(entries)
            await safe_edit_or_recreate(
                bot, session, user, text,
                calendar_keyboard(year, month, symbols),
                prefer_message_id=_clicked_id(callback),
            )


@router.callback_query(F.data == CB_CALENDAR)
async def on_open(callback: CallbackQuery, bot: Bot) -> None:
    d = today_date()
    await _render(bot, callback, d.year, d.month)
    await callback.answer()


@router.callback_query(F.data.startswith("cal:nav:"))
async def on_nav(callback: CallbackQuery, bot: Bot) -> None:
    # формат: cal:nav:<YYYY-MM>
    ym = callback.data.split(":", 2)[2]
    try:
        year, month = (int(x) for x in ym.split("-", 1))
    except ValueError:
        d = today_date()
        year, month = d.year, d.month
    await _render(bot, callback, year, month)
    await callback.answer()


@router.callback_query(F.data.startswith("cal:day:"))
async def on_day(callback: CallbackQuery) -> None:
    # формат: cal:day:<ISO-date> — показать записи дня всплывающим окном
    iso = callback.data.split(":", 2)[2]
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        await callback.answer()
        return

    tg_id = callback.from_user.id
    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, tg_id)
        entries = await crud.get_headache_entries_between_dates(
            session, user, day, day
        )
    await callback.answer(cv.day_popup_text(entries, day), show_alert=True)


@router.callback_query(F.data == CB_CAL_NOOP)
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()
