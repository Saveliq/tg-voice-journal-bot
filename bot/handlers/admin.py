"""Админские команды (доступны только пользователю с config.admin_id)."""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.db import crud
from bot.db.session import async_session_factory
from bot.handlers.start import delete_user_message
from bot.services.headache import send_daily_prompt
from bot.services.scheduler import dispatch_due_prompts
from bot.services.singleton_message import user_lock

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == settings.admin_id


@router.message(Command("testprompt"))
async def cmd_testprompt(message: Message, bot: Bot) -> None:
    """Прислать себе вопрос о ГБ прямо сейчас (для тестирования расписания)."""
    if not _is_admin(message):
        await delete_user_message(message)
        return

    tg_id = message.from_user.id
    await delete_user_message(message)
    async with user_lock(tg_id):
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, tg_id)
            await send_daily_prompt(bot, session, user)
    logger.info("Админ %s запросил тестовый промпт", tg_id)


@router.message(Command("testbroadcast"))
async def cmd_testbroadcast(message: Message, bot: Bot) -> None:
    """Принудительно запустить рассылку всем, у кого сейчас наступило время."""
    if not _is_admin(message):
        await delete_user_message(message)
        return

    await delete_user_message(message)
    await dispatch_due_prompts(bot)
    logger.info("Админ %s запустил dispatch_due_prompts вручную", message.from_user.id)
