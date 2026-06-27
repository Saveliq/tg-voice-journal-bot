"""Логика «единственного сообщения» бота.

Это ЕДИНСТВЕННОЕ место в коде, откуда отправляется/редактируется главное
сообщение интерфейса. Хендлеры обязаны звать только эти функции и никогда
не вызывать bot.send_message / bot.edit_message_text для основного UI напрямую.

Дополнительно здесь живёт реестр per-user блокировок (asyncio.Lock), чтобы
сериализовать обработку сообщений одного пользователя и не ловить гонки при
параллельных edit_message_text одного и того же message_id.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import crud
from bot.db.models import User

logger = logging.getLogger(__name__)

# Реестр блокировок по telegram_id. defaultdict гарантирует один Lock на юзера.
_user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

# Подстроки ошибок Telegram, означающие, что сообщение нельзя отредактировать.
_NOT_EDITABLE_MARKERS = (
    "message to edit not found",
    "message can't be edited",
    "message identifier is not specified",
    "MESSAGE_ID_INVALID",
)


def user_lock(telegram_id: int) -> asyncio.Lock:
    """Вернуть (создав при необходимости) блокировку для пользователя."""
    return _user_locks[telegram_id]


def _is_not_editable_error(err: TelegramBadRequest) -> bool:
    msg = (err.message or "").lower()
    return any(marker.lower() in msg for marker in _NOT_EDITABLE_MARKERS)


async def _send_new(
    bot: Bot,
    session: AsyncSession,
    user: User,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
) -> None:
    """Отправить новое главное сообщение и сохранить его id в БД."""
    sent = await bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        reply_markup=keyboard,
    )
    await crud.set_pinned_message_id(session, user, sent.message_id)


async def safe_edit_or_recreate(
    bot: Bot,
    session: AsyncSession,
    user: User,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    *,
    prefer_message_id: int | None = None,
) -> None:
    """Обновить главное сообщение: отредактировать, иначе пересоздать.

    1. Нет pinned_message_id → отправляем новое.
    2. Пытаемся edit_message_text.
    3. Если Telegram говорит, что редактировать нельзя → удаляем старое
       (best-effort) и отправляем новое, обновив id в БД.
    4. Любая другая ошибка — логируем и пробрасываем, не заглатываем.

    ``prefer_message_id`` — id сообщения, которое заведомо является «живым»
    (например, то, на котором пользователь нажал inline-кнопку). Если оно
    отличается от сохранённого в БД, мы считаем его актуальным и синхронизируем
    pinned_message_id с ним. Это защищает от «протухшего» pinned_message_id
    после перезапусков бота, из-за которого сообщение пересоздавалось вместо
    редактирования.
    """
    if prefer_message_id is not None and prefer_message_id != user.pinned_message_id:
        await crud.set_pinned_message_id(session, user, prefer_message_id)

    if user.pinned_message_id is None:
        await _send_new(bot, session, user, text, keyboard)
        return

    try:
        await bot.edit_message_text(
            text=text,
            chat_id=user.telegram_id,
            message_id=user.pinned_message_id,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as err:
        # «Сообщение не изменилось» — не ошибка, просто игнорируем.
        if "message is not modified" in (err.message or "").lower():
            return

        if not _is_not_editable_error(err):
            logger.error(
                "Неожиданная ошибка edit_message_text для user=%s: %s",
                user.telegram_id,
                err,
            )
            raise

        logger.info(
            "Сообщение %s нельзя отредактировать (%s) — пересоздаю.",
            user.pinned_message_id,
            err.message,
        )
        # Старое сообщение могло быть удалено пользователем вручную — best-effort.
        try:
            await bot.delete_message(
                chat_id=user.telegram_id,
                message_id=user.pinned_message_id,
            )
        except TelegramBadRequest:
            pass
        await _send_new(bot, session, user, text, keyboard)
