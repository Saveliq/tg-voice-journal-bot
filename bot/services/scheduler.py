"""Планировщик ежедневной рассылки вопроса о головной боли.

Каждый пользователь задаёт своё время (User.prompt_time, HH:MM в своём поясе).
Планировщик раз в минуту проверяет, у кого локальное время совпало, и шлёт
вопрос. Это проще и надёжнее, чем держать отдельную задачу на каждого.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.db import crud
from bot.db.session import async_session_factory
from bot.services.headache import send_daily_prompt
from bot.services.time_utils import local_now

logger = logging.getLogger(__name__)


async def dispatch_due_prompts(bot: Bot) -> None:
    """Разослать вопрос пользователям, у кого ЛОКАЛЬНОЕ время = их prompt_time.

    Раз в минуту проверяем каждого включённого пользователя в его поясе.
    """
    async with async_session_factory() as session:
        users = await crud.get_enabled_users(session)

    due = [u for u in users if local_now(u).strftime("%H:%M") == u.prompt_time]
    if not due:
        return

    logger.info("Напоминание о ГБ: %d пользователей", len(due))
    for user in due:
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
