"""Хендлеры дневника головной боли: пошаговый опрос + ввод препарата (FSM).

Флоу:
    [промпт] Болела голова?  ──Нет──►  запись (не болела) ──► лента
                             └──Да───►  запись (болела)
                                        Принимали обезболивающие?
                                          ├─Нет─► лента
                                          └─Да──► Какой препарат?
                                                   ├─выбор из списка ─► лента
                                                   └─Другой ─(текст)─► лента

Опрос редактирует ОДНО сообщение (то, на котором нажата кнопка). В конце:
- если опрос шёл на «живом» сообщении-ленте (ручной запуск кнопкой) — сообщение
  возвращается к ленте на месте;
- если опрос пришёл отдельным промптом (ежедневная рассылка / /testprompt) —
  это сообщение удаляется, а основная лента обновляется отдельно.
Так после прохождения опроса не остаётся лишних сообщений.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.db import crud
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.keyboards import (
    CB_HD_START,
    feed_keyboard,
    headache_ask_keyboard,
    headache_date_picker_keyboard,
    medication_keyboard,
    painkiller_ask_keyboard,
)
from bot.services import headache as hd
from bot.services.feed import render_today_feed
from bot.services.singleton_message import safe_edit_or_recreate, user_lock

logger = logging.getLogger(__name__)
router = Router(name="headache")

TRANSIENT_DELAY = 2.5  # сек — показ подтверждения перед возвратом к ленте


class HeadacheStates(StatesGroup):
    awaiting_medication = State()


def _clicked_id(callback: CallbackQuery) -> int | None:
    return callback.message.message_id if callback.message else None


async def _edit(
    bot: Bot,
    chat_id: int,
    msg_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
) -> None:
    """Отредактировать конкретное сообщение опроса (best-effort)."""
    try:
        await bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard
        )
    except TelegramBadRequest as err:
        if "message is not modified" in (err.message or "").lower():
            return
        logger.info("Не удалось отредактировать сообщение опроса %s: %s", msg_id, err.message)


async def _finish(
    bot: Bot, session, user, chat_id: int, wizard_id: int, confirm_text: str
) -> None:
    """Показать подтверждение, затем вернуть «главное меню» (ленту).

    Если опрос шёл на живом сообщении-ленте — возвращаем ленту на том же
    сообщении. Иначе (отдельный промпт) — удаляем его и обновляем основную ленту.
    """
    await _edit(bot, chat_id, wizard_id, confirm_text, None)
    await asyncio.sleep(TRANSIENT_DELAY)

    feed_text = await render_today_feed(session, user)
    if user.pinned_message_id == wizard_id:
        # Опрос шёл прямо на живом сообщении — возвращаем ленту на месте.
        await _edit(bot, chat_id, wizard_id, feed_text, feed_keyboard())
    else:
        # Отдельный промпт — удаляем его и обновляем основную ленту.
        try:
            await bot.delete_message(chat_id=chat_id, message_id=wizard_id)
        except TelegramBadRequest:
            pass
        await safe_edit_or_recreate(bot, session, user, feed_text, feed_keyboard())


# --- Ручной запуск: выбор даты записи (кнопка «🤕 Голова» на ленте) ---

@router.callback_query(F.data == CB_HD_START)
async def on_start(callback: CallbackQuery, bot: Bot) -> None:
    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            # Запуск с ленты: считаем это сообщение «живым» (адаптируем как pinned),
            # чтобы в конце вернуть ленту на месте, не плодя сообщений.
            if msg_id is not None:
                await crud.set_pinned_message_id(session, user, msg_id)
                await _edit(
                    bot, tg_id, msg_id,
                    "На какой день сделать запись?",
                    headache_date_picker_keyboard(hd.today_date(user)),
                )
    await callback.answer()


# --- Выбрана дата записи → начать опрос на эту дату ---

@router.callback_query(F.data.startswith("hd:pick:"))
async def on_pick_date(callback: CallbackQuery, bot: Bot) -> None:
    # формат: hd:pick:<ISO-date>
    iso = callback.data.split(":", 2)[2]
    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            try:
                entry_date = date.fromisoformat(iso)
            except ValueError:
                entry_date = hd.today_date(user)
            # Это «живое» сообщение — адаптируем как pinned, опрос пойдёт на месте.
            if msg_id is not None:
                await crud.set_pinned_message_id(session, user, msg_id)
                await _edit(
                    bot, tg_id, msg_id, hd.PROMPT_TEXT,
                    headache_ask_keyboard(entry_date),
                )
    await callback.answer()


# --- Болела голова? ---

@router.callback_query(F.data.startswith("hd:had:"))
async def on_had(callback: CallbackQuery, bot: Bot) -> None:
    # формат: hd:had:<0|1>:<ISO-date>
    _, _, flag, iso = callback.data.split(":", 3)
    had = flag == "1"

    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            try:
                entry_date = date.fromisoformat(iso)
            except ValueError:
                entry_date = hd.today_date(user)
            entry = await crud.create_headache_entry(session, user, entry_date, had)

            if not had:
                await _finish(
                    bot, session, user, tg_id, msg_id,
                    hd.confirm_no_headache(entry_date),
                )
            else:
                await _edit(
                    bot, tg_id, msg_id, hd.PAINKILLER_TEXT,
                    painkiller_ask_keyboard(entry.id),
                )
    await callback.answer()


# --- Принимали обезболивающие? ---

@router.callback_query(F.data.startswith("hd:pk:"))
async def on_painkiller(callback: CallbackQuery, bot: Bot) -> None:
    # формат: hd:pk:<0|1>:<entry_id>
    _, _, flag, entry_id_raw = callback.data.split(":", 3)
    took = flag == "1"
    entry_id = int(entry_id_raw)

    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            entry = await crud.get_headache_entry(session, entry_id)
            if entry is None:
                await callback.answer("Запись не найдена", show_alert=True)
                return
            await crud.update_headache_entry(session, entry, took_painkiller=took)

            if not took:
                await _finish(
                    bot, session, user, tg_id, msg_id,
                    hd.confirm_headache(None, took_painkiller=False),
                )
            else:
                meds = await crud.list_medications(session, user)
                await _edit(
                    bot, tg_id, msg_id, hd.MEDICATION_TEXT,
                    medication_keyboard(entry.id, meds),
                )
    await callback.answer()


# --- Выбор препарата из списка ---

@router.callback_query(F.data.startswith("hd:med:"))
async def on_medication_pick(callback: CallbackQuery, bot: Bot) -> None:
    # формат: hd:med:<entry_id>:<med_id>
    _, _, entry_id_raw, med_id_raw = callback.data.split(":", 3)
    entry_id = int(entry_id_raw)
    med_id = int(med_id_raw)

    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            entry = await crud.get_headache_entry(session, entry_id)
            med = await crud.get_medication(session, med_id)
            if entry is None or med is None:
                await callback.answer("Запись не найдена", show_alert=True)
                return
            await crud.update_headache_entry(session, entry, medication_id=med.id)
            await _finish(
                bot, session, user, tg_id, msg_id,
                hd.confirm_headache(med.name, took_painkiller=True),
            )
    await callback.answer()


# --- Ввод нового препарата (переход в FSM) ---

@router.callback_query(F.data.startswith("hd:newmed:"))
async def on_new_medication(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # формат: hd:newmed:<entry_id>
    entry_id = int(callback.data.split(":", 2)[2])
    tg_id = callback.from_user.id
    msg_id = _clicked_id(callback)

    await state.set_state(HeadacheStates.awaiting_medication)
    await state.update_data(entry_id=entry_id, wizard_id=msg_id)

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await _edit(bot, tg_id, msg_id, hd.MEDICATION_TEXT, None)
    await callback.answer()


@router.message(HeadacheStates.awaiting_medication, F.text)
async def on_medication_text(message: Message, bot: Bot, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return
    tg_id = message.from_user.id
    name = message.text.strip()

    data = await state.get_data()
    entry_id = data.get("entry_id")
    wizard_id = data.get("wizard_id")
    await state.clear()

    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            entry = await crud.get_headache_entry(session, entry_id) if entry_id else None
            await delete_user_message(message)

            if entry is None or not name or wizard_id is None:
                feed_text = await render_today_feed(session, user)
                await safe_edit_or_recreate(bot, session, user, feed_text, feed_keyboard())
                return

            med = await crud.get_or_create_medication(session, user, name)
            await crud.update_headache_entry(session, entry, medication_id=med.id)
            await _finish(
                bot, session, user, tg_id, wizard_id,
                hd.confirm_headache(med.name, took_painkiller=True),
            )
