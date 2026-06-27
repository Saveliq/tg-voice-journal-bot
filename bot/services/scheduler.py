"""Планировщик ежедневной рассылки вопроса о головной боли.

Каждый пользователь задаёт своё время (User.prompt_time, HH:MM в UTC).
Планировщик раз в минуту проверяет, кому пора, и шлёт вопрос. Это проще и
надёжнее, чем держать отдельную задачу на каждого пользователя.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.db import crud
from bot.db.session import async_session_factory
from bot.services.headache import send_daily_prompt

logger = logging.getLogger(__name__)


async def dispatch_due_prompts(bot: Bot) -> None:
    """Разослать вопрос пользователям, чьё время напоминания = текущая минута (UTC)."""
    now = datetime.now(timezone.utc)
    hh_mm = now.strftime("%H:%M")

    async with async_session_factory() as session:
        users = await crud.get_users_for_prompt_time(session, hh_mm)

    if not users:
        return

    logger.info("Напоминание о ГБ (%s UTC): %d пользователей", hh_mm, len(users))
    for user in users:
        async with async_session_factory() as session:
            fresh = await crud.get_or_create_user(session, user.telegram_id)
            await send_daily_prompt(bot, session, fresh)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    # Каждую минуту в :00 секунд — проверяем, кому пора.
    scheduler.add_job(
        dispatch_due_prompts,
        trigger=CronTrigger(second=0),
        kwargs={"bot": bot},
        id="headache_prompt_dispatch",
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info("Планировщик запущен: проверка напоминаний раз в минуту (UTC)")
    return scheduler
