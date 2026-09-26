"""Планировщик напоминаний и обновления ленты в полночь.

Раз в минуту проверяет локальное время в часовом поясе пользователя.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.db import crud
from bot.db.session import async_session_factory
from bot.keyboards import feed_keyboard
from bot.services.feed import render_today_feed
from bot.services.headache import send_daily_prompt
from bot.services.pill import send_daily_prompt as send_pill_prompt
from bot.services.singleton_message import safe_edit_or_recreate, user_lock
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

        async with user_lock(user.telegram_id), async_session_factory() as session:
            # Учитываем изменение настроек после получения списка пользователей.
            fresh = await crud.get_or_create_user(session, user.telegram_id)
            hh_mm = local_now(fresh).strftime("%H:%M")
            if fresh.prompt_enabled and hh_mm == fresh.prompt_time:
                await send_daily_prompt(bot, session, fresh)
            if fresh.pill_prompt_enabled and hh_mm == fresh.pill_prompt_time:
                await send_pill_prompt(bot, fresh)


async def refresh_midnight_feeds(bot: Bot, dispatcher: Dispatcher) -> None:
    """Обновить главное сообщение на новый день в локальные 00:00."""
    async with async_session_factory() as session:
        users = await crud.get_all_users(session)

    for user in users:
        if user.pinned_message_id is None or local_now(user).strftime("%H:%M") != "00:00":
            continue
        try:
            async with user_lock(user.telegram_id):
                async with async_session_factory() as session:
                    # Настройки и главное сообщение могли измениться до получения блокировки.
                    fresh = await crud.get_user(session, user.telegram_id)
                    if (
                        fresh is None
                        or fresh.pinned_message_id is None
                        or local_now(fresh).strftime("%H:%M") != "00:00"
                    ):
                        continue
                    text = await render_today_feed(session, fresh)
                    await safe_edit_or_recreate(bot, session, fresh, text, feed_keyboard(fresh))
                    # После возврата к ленте ввод снова относится к сегодняшнему дню.
                    state = dispatcher.fsm.get_context(
                        bot=bot, chat_id=fresh.telegram_id, user_id=fresh.telegram_id,
                    )
                    await state.clear()
        except TelegramForbiddenError:
            logger.info("Пользователь %s заблокировал бота, пропуск обновления ленты", user.telegram_id)
        except Exception:  # noqa: BLE001 — ошибка одного чата не мешает остальным
            logger.exception("Не удалось обновить ленту в полночь user=%s", user.telegram_id)


def setup_scheduler(bot: Bot, dispatcher: Dispatcher) -> AsyncIOScheduler:
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
    scheduler.add_job(
        refresh_midnight_feeds,
        trigger=CronTrigger(second=0, timezone="UTC"),
        kwargs={"bot": bot, "dispatcher": dispatcher},
        id="midnight_feed_refresh",
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info("Планировщик запущен: проверка напоминаний и смены дня раз в минуту (UTC)")
    return scheduler
