"""Планировщик ежедневных напоминаний о головной боли и таблетке.

Раз в минуту проверяет оба независимых расписания в часовом поясе пользователя.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.db import crud
from bot.db.session import async_session_factory
from bot.services.headache import send_daily_prompt
from bot.services.pill import send_daily_prompt as send_pill_prompt
from bot.services.time_utils import local_now

logger = logging.getLogger(__name__)


async def dispatch_due_prompts(bot: Bot) -> None:
    """Разослать включённые напоминания при совпадении локального времени."""
    async with async_session_factory() as session:
        users = await crud.get_enabled_users(session)

    for user in users:
        hh_mm = local_now(user).strftime("%H:%M")
        headache_due = user.prompt_enabled and hh_mm == user.prompt_time
        pill_due = user.pill_prompt_enabled and hh_mm == user.pill_prompt_time
        if not (headache_due or pill_due):
            continue

        async with async_session_factory() as session:
            # Учитываем изменение настроек после получения списка пользователей.
            fresh = await crud.get_or_create_user(session, user.telegram_id)
            hh_mm = local_now(fresh).strftime("%H:%M")
            if fresh.prompt_enabled and hh_mm == fresh.prompt_time:
                await send_daily_prompt(bot, session, fresh)
            if fresh.pill_prompt_enabled and hh_mm == fresh.pill_prompt_time:
                await send_pill_prompt(bot, fresh)


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
