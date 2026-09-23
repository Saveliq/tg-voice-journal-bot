"""Настройки ежедневных напоминаний о головной боли и таблетке."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import crud
from bot.db.models import User
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.keyboards import (
    CB_SET_PILL_TIME,
    CB_SET_PILL_TOGGLE,
    CB_SET_TIME,
    CB_SET_TOGGLE,
    CB_SET_TZ,
    CB_SETTINGS,
    TIMEZONES,
    settings_keyboard,
    timezone_keyboard,
)
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
from bot.services.time_utils import local_now

logger = logging.getLogger(__name__)
router = Router(name="settings")

_TIME_RE = re.compile(r"^([01]?\d|2[0-3])[:.\s]([0-5]?\d)$")
_TZ_LABELS = {iana: label for label, iana in TIMEZONES}

ASK_TIME_TEXT = (
    "🕐 <b>Во сколько присылать напоминание {reminder}?</b>\n\n"
    "Отправь время в формате <b>ЧЧ:ММ</b> (в твоём часовом поясе), "
    "например <code>20:00</code>."
)

ASK_TZ_TEXT = "🌍 <b>Выбери часовой пояс</b>"


class SettingsStates(StatesGroup):
    awaiting_time = State()
    awaiting_pill_time = State()


def parse_time(value: str) -> str | None:
    """Нормализовать пользовательский ввод времени в 'HH:MM' или None."""
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"


def _settings_text(user: User) -> str:
    status = "включено ✅" if user.prompt_enabled else "выключено 🔕"
    pill_status = "включено ✅" if user.pill_prompt_enabled else "выключено 🔕"
    tz_label = _TZ_LABELS.get(user.timezone, user.timezone)
    local = local_now(user).strftime("%H:%M")
    return (
        "⚙️ <b>Настройки напоминаний</b>\n\n"
        "🤕 <b>Головная боль</b>\n"
        f"Время: <b>{user.prompt_time}</b>\n"
        f"Напоминание: <b>{status}</b>\n\n"
        "💊 <b>Таблетка</b>\n"
        f"Время: <b>{user.pill_prompt_time}</b>\n"
        f"Напоминание: <b>{pill_status}</b>\n\n"
        f"Часовой пояс: <b>{tz_label}</b>\n"
        f"Сейчас у тебя: <b>{local}</b>"
    )


def _clicked_id(callback: CallbackQuery) -> int | None:
    return callback.message.message_id if callback.message else None


@router.callback_query(F.data == CB_SETTINGS)
async def on_settings(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await safe_edit_or_recreate(
                bot, session, user, _settings_text(user),
                settings_keyboard(user.prompt_enabled, user.pill_prompt_enabled),
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data.in_({CB_SET_TOGGLE, CB_SET_PILL_TOGGLE}))
async def on_toggle(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            if callback.data == CB_SET_PILL_TOGGLE:
                await crud.set_pill_prompt_enabled(session, user, not user.pill_prompt_enabled)
            else:
                await crud.set_prompt_enabled(session, user, not user.prompt_enabled)
            await safe_edit_or_recreate(
                bot, session, user, _settings_text(user),
                settings_keyboard(user.prompt_enabled, user.pill_prompt_enabled),
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data.in_({CB_SET_TIME, CB_SET_PILL_TIME}))
async def on_set_time(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    tg_id = callback.from_user.id
    is_pill = callback.data == CB_SET_PILL_TIME
    await state.set_state(
        SettingsStates.awaiting_pill_time if is_pill else SettingsStates.awaiting_time
    )
    ask_text = ASK_TIME_TEXT.format(reminder="о таблетке" if is_pill else "о головной боли")
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await safe_edit_or_recreate(
                bot, session, user, ask_text, None,
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data == CB_SET_TZ)
async def on_set_tz(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await safe_edit_or_recreate(
                bot, session, user, ASK_TZ_TEXT, timezone_keyboard(),
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer()


@router.callback_query(F.data.startswith("tz:set:"))
async def on_tz_pick(callback: CallbackQuery, bot: Bot) -> None:
    # формат: tz:set:<IANA>
    tz_name = callback.data.split(":", 2)[2]
    tg_id = callback.from_user.id
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await crud.set_timezone(session, user, tz_name)
            await safe_edit_or_recreate(
                bot, session, user, _settings_text(user),
                settings_keyboard(user.prompt_enabled, user.pill_prompt_enabled),
                prefer_message_id=_clicked_id(callback),
            )
    await callback.answer("Часовой пояс обновлён ✅")


@router.message(SettingsStates.awaiting_pill_time, F.text)
@router.message(SettingsStates.awaiting_time, F.text)
async def on_time_text(message: Message, bot: Bot, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return
    tg_id = message.from_user.id
    hh_mm = parse_time(message.text)
    is_pill = await state.get_state() == SettingsStates.awaiting_pill_time.state

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await delete_user_message(message)

            if hh_mm is None:
                # Неверный формат — остаёмся в состоянии ввода, подсказываем.
                await safe_edit_or_recreate(
                    bot, session, user,
                    "⚠️ Не понял время. Нужен формат <b>ЧЧ:ММ</b>, например <code>09:30</code>.",
                    None,
                    prefer_message_id=user.pinned_message_id,
                )
                return

            if is_pill:
                await crud.set_pill_prompt_time(session, user, hh_mm)
            else:
                await crud.set_prompt_time(session, user, hh_mm)
            await state.clear()
            # Возврат к экрану настроек с обновлённым временем.
            await safe_edit_or_recreate(
                bot, session, user, _settings_text(user),
                settings_keyboard(user.prompt_enabled, user.pill_prompt_enabled),
                prefer_message_id=user.pinned_message_id,
            )
