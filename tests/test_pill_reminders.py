"""Regression checks with an isolated in-memory DB and no Telegram requests."""
from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Never connect to the database configured in the developer's .env.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, EditMessageText, SendMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db import crud
from bot.db import session as db_session
from bot.db.models import Base, SourceType, User
from bot.handlers import pill as pill_handler
from bot.handlers import settings as settings_handler
from bot.keyboards import (
    CB_PILL_MENU,
    CB_PILL_TAKEN,
    CB_STATS,
    feed_keyboard,
    CB_SET_PILL_TIME,
    CB_SET_PILL_TOGGLE,
    CB_SET_TIME,
    CB_SET_TOGGLE,
)
from bot.services import headache, pill, scheduler
from bot.services.time_utils import local_today


def callback(data: str):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=101),
        message=SimpleNamespace(message_id=17, chat=SimpleNamespace(id=101)),
        answer=AsyncMock(),
    )


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.addAsyncCleanup(self.engine.dispose)
        self.bot = AsyncMock()

    async def add_user(self, telegram_id=101, **overrides):
        fields = dict(
            telegram_id=telegram_id, timezone="Europe/Moscow",
            prompt_time="20:00", prompt_enabled=True,
            pill_prompt_time="20:00", pill_prompt_enabled=True,
        )
        fields.update(overrides)
        async with self.factory() as session:
            user = User(**fields)
            session.add(user)
            await session.commit()
        return user

    async def load_user(self):
        async with self.factory() as session:
            return await crud.get_user(session, 101)

    async def test_scheduler_respects_each_time_toggle_and_timezone(self):
        await self.add_user(1, prompt_enabled=False)
        await self.add_user(2, pill_prompt_enabled=False)
        await self.add_user(3, timezone="UTC")
        await self.add_user(4)
        await self.add_user(5, prompt_enabled=False, pill_prompt_time="07:00")
        await self.add_user(6, prompt_enabled=False, pill_prompt_enabled=False)
        await self.add_user(7, timezone="Europe/Samara", pill_prompt_time="21:00")
        await self.add_user(8, timezone="UTC", pill_prompt_time="17:00")
        with (
            patch.object(scheduler, "async_session_factory", self.factory),
            patch("bot.services.time_utils.datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc)
            await scheduler.dispatch_due_prompts(self.bot)
        sent = [
            (call.kwargs["chat_id"], call.kwargs["text"])
            for call in self.bot.send_message.await_args_list
        ]
        self.assertCountEqual(sent, [
            (1, pill.PROMPT_TEXT), (2, headache.PROMPT_TEXT),
            (4, headache.PROMPT_TEXT), (4, pill.PROMPT_TEXT),
            (7, pill.PROMPT_TEXT), (8, pill.PROMPT_TEXT),
        ])

    async def test_midnight_refresh_uses_local_day_even_without_reminders(self):
        self.bot.id = 1
        dp = Dispatcher()
        self.addAsyncCleanup(dp.storage.close)
        user = await self.add_user(
            pinned_message_id=17, prompt_enabled=False, pill_prompt_enabled=False,
            pill_taken_date=date(2026, 9, 25),
        )
        await self.add_user(102, timezone="UTC", pinned_message_id=18)
        await self.add_user(103, timezone="Europe/Samara", pinned_message_id=19)
        await self.add_user(104, pinned_message_id=None)
        state = dp.fsm.get_context(bot=self.bot, chat_id=101, user_id=101)
        await state.set_state("DayView:active")
        await state.update_data(day="2026-09-24")
        async with self.factory() as session:
            await crud.add_entry(session, user, "Вчерашняя запись", SourceType.text,
                                 created_at=datetime(2026, 9, 25, 20, 59))
            await crud.add_entry(session, user, "Новая запись", SourceType.text,
                                 created_at=datetime(2026, 9, 25, 21, 0))
        with (
            patch.object(scheduler, "async_session_factory", self.factory),
            patch("bot.services.time_utils.datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = datetime(2026, 9, 25, 20, 59, tzinfo=timezone.utc)
            await scheduler.refresh_midnight_feeds(self.bot, dp)
            self.bot.edit_message_text.assert_not_awaited()
            clock.now.return_value = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)
            await scheduler.refresh_midnight_feeds(self.bot, dp)
            clock.now.return_value += timedelta(minutes=1)
            await scheduler.refresh_midnight_feeds(self.bot, dp)
        self.bot.edit_message_text.assert_awaited_once()
        edit = self.bot.edit_message_text.await_args.kwargs
        self.assertEqual((edit["chat_id"], edit["message_id"]), (101, 17))
        self.assertIn("Суббота, 26 сентября", edit["text"])
        self.assertIn("Новая запись", edit["text"])
        self.assertNotIn("Вчерашняя запись", edit["text"])
        self.assertEqual(edit["reply_markup"].inline_keyboard[1][0].text, "💊 Таблетки")
        self.assertIsNone(await state.get_state())
        self.assertEqual(await state.get_data(), {})
        self.bot.send_message.assert_not_awaited()
        self.assertEqual((await self.load_user()).pill_taken_date, date(2026, 9, 25))

    async def test_midnight_supports_half_hour_timezone_and_keeps_new_day_pill(self):
        self.bot.id = 1
        dp = Dispatcher()
        self.addAsyncCleanup(dp.storage.close)
        await self.add_user(timezone="Asia/Kolkata", pinned_message_id=17,
                            pill_taken_date=date(2026, 9, 26))
        with (
            patch.object(scheduler, "async_session_factory", self.factory),
            patch("bot.services.time_utils.datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = datetime(2026, 9, 25, 18, 30, tzinfo=timezone.utc)
            await scheduler.refresh_midnight_feeds(self.bot, dp)
        self.bot.edit_message_text.assert_awaited_once()
        edit = self.bot.edit_message_text.await_args.kwargs
        self.assertIn("26 сентября", edit["text"])
        self.assertEqual(edit["reply_markup"].inline_keyboard[1][0].text, "✅ Выпил")

    async def test_midnight_blocked_chat_does_not_stop_other_users(self):
        self.bot.id = 1
        dp = Dispatcher()
        self.addAsyncCleanup(dp.storage.close)
        await self.add_user(pinned_message_id=17)
        await self.add_user(102, pinned_message_id=18)
        self.bot.edit_message_text.side_effect = [TelegramForbiddenError(
            method=EditMessageText(chat_id=101, message_id=17, text="test"),
            message="bot was blocked by the user",
        ), None]
        with (
            patch.object(scheduler, "async_session_factory", self.factory),
            patch("bot.services.time_utils.datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)
            await scheduler.refresh_midnight_feeds(self.bot, dp)
        self.assertEqual(
            [c.kwargs["chat_id"] for c in self.bot.edit_message_text.await_args_list],
            [101, 102],
        )

    async def test_scheduler_registers_midnight_refresh_every_minute(self):
        dp = Dispatcher()
        self.addAsyncCleanup(dp.storage.close)
        with patch.object(scheduler.AsyncIOScheduler, "start"):
            jobs = scheduler.setup_scheduler(self.bot, dp)
        job = jobs.get_job("midnight_feed_refresh")
        self.assertIsNotNone(job)
        self.assertIs(job.func, scheduler.refresh_midnight_feeds)
        self.assertEqual(job.kwargs, {"bot": self.bot, "dispatcher": dp})
        now = datetime(2026, 9, 25, 18, 29, 59, tzinfo=timezone.utc)
        first = job.trigger.get_next_fire_time(None, now)
        second = job.trigger.get_next_fire_time(first, first)
        self.assertEqual(first, now + timedelta(seconds=1))
        self.assertEqual(second - first, timedelta(minutes=1))

    async def test_new_user_uses_configured_default(self):
        with patch.object(crud.settings, "pill_prompt_time", "08:45"):
            async with self.factory() as session:
                user = await crud.get_or_create_user(session, 101)
        saved = await self.load_user()
        self.assertEqual(saved.pill_prompt_time, "08:45")
        self.assertTrue(saved.pill_prompt_enabled)
        self.assertEqual(saved.id, user.id)

    async def test_settings_save_only_selected_time(self):
        await self.add_user()
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=101, user_id=101))
        self.addAsyncCleanup(state.storage.close)
        with (
            patch.object(settings_handler, "async_session_factory", self.factory),
            patch.object(settings_handler, "safe_edit_or_recreate", new_callable=AsyncMock) as render,
        ):
            for data, value, expected_headache, expected_pill, prompt_word in [
                (CB_SET_PILL_TIME, "9:05", "20:00", "09:05", "о таблетке"),
                (CB_SET_TIME, "21:30", "21:30", "09:05", "о головной боли"),
            ]:
                with self.subTest(data=data):
                    await settings_handler.on_set_time(callback(data), self.bot, state)
                    self.assertIn(prompt_word, render.await_args.args[3])
                    message = SimpleNamespace(
                        from_user=SimpleNamespace(id=101), text=value, delete=AsyncMock()
                    )
                    await settings_handler.on_time_text(message, self.bot, state)
                    saved = await self.load_user()
                    self.assertEqual(saved.prompt_time, expected_headache)
                    self.assertEqual(saved.pill_prompt_time, expected_pill)
                    self.assertIsNone(await state.get_state())
                    message.delete.assert_awaited_once()
                    self.assertIn(expected_pill, render.await_args.args[3])

    async def test_invalid_pill_time_keeps_settings_and_input_state(self):
        await self.add_user()
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=101, user_id=101))
        self.addAsyncCleanup(state.storage.close)
        await state.set_state(settings_handler.SettingsStates.awaiting_pill_time)
        with (
            patch.object(settings_handler, "async_session_factory", self.factory),
            patch.object(settings_handler, "safe_edit_or_recreate", new_callable=AsyncMock),
        ):
            for value in ("24:00", "12:60", "завтра"):
                message = SimpleNamespace(
                    from_user=SimpleNamespace(id=101), text=value, delete=AsyncMock()
                )
                await settings_handler.on_time_text(message, self.bot, state)
                self.assertEqual(
                    await state.get_state(), settings_handler.SettingsStates.awaiting_pill_time.state
                )
                saved = await self.load_user()
                self.assertEqual((saved.prompt_time, saved.pill_prompt_time), ("20:00", "20:00"))

    async def test_settings_toggle_each_reminder_independently(self):
        await self.add_user()
        with (
            patch.object(settings_handler, "async_session_factory", self.factory),
            patch.object(settings_handler, "safe_edit_or_recreate", new_callable=AsyncMock),
        ):
            for data, expected in [
                (CB_SET_PILL_TOGGLE, (True, False)),
                (CB_SET_TOGGLE, (False, False)),
                (CB_SET_PILL_TOGGLE, (False, True)),
            ]:
                await settings_handler.on_toggle(callback(data), self.bot)
                saved = await self.load_user()
                self.assertEqual((saved.prompt_enabled, saved.pill_prompt_enabled), expected)

    async def test_prompt_has_exact_text_and_only_yes(self):
        user = await self.add_user()
        await pill.send_daily_prompt(self.bot, user)
        sent = self.bot.send_message.await_args.kwargs
        self.assertEqual(sent["chat_id"], user.telegram_id)
        self.assertEqual(sent["text"], "выпил таблетку ?")
        rows = sent["reply_markup"].inline_keyboard
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 1)
        self.assertEqual((rows[0][0].text, rows[0][0].callback_data), ("Да", CB_PILL_TAKEN))

    async def take_pill(self, data):
        query = callback(data)
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=101, user_id=101))
        self.addAsyncCleanup(state.storage.close)
        self.bot.send_message.return_value = SimpleNamespace(message_id=25)
        with (
            patch.object(pill_handler, "async_session_factory", self.factory),
            patch.object(pill_handler.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            await pill_handler.on_pill_taken(query, self.bot, state)
        query.answer.assert_awaited_once_with()
        sleep.assert_awaited_once_with(5)
        self.bot.send_message.assert_awaited_once_with(
            chat_id=101, text=pill.CONFIRM_TEXT, reply_markup=None,
        )
        self.assertIsNone(await state.get_state())
        saved = await self.load_user()
        self.assertEqual(saved.pill_taken_date, local_today(saved))
        buttons = [button for row in feed_keyboard(saved).inline_keyboard for button in row]
        self.assertEqual(next(b.text for b in buttons if b.callback_data == CB_PILL_MENU), "✅ Выпил")
        return saved

    async def test_menu_marks_taken_without_deleting_main_message(self):
        await self.add_user(pinned_message_id=11)
        saved = await self.take_pill(CB_PILL_MENU)
        self.assertEqual(saved.pinned_message_id, 17)
        self.bot.delete_message.assert_awaited_once_with(chat_id=101, message_id=25)
        edit = self.bot.edit_message_text.await_args.kwargs
        self.assertEqual(edit["message_id"], 17)
        self.assertEqual(edit["reply_markup"], feed_keyboard(saved))

    async def test_yes_closes_reminder_and_updates_main_menu(self):
        await self.add_user(pinned_message_id=11)
        saved = await self.take_pill(CB_PILL_TAKEN)
        self.assertEqual(saved.pinned_message_id, 11)
        deleted = [c.kwargs["message_id"] for c in self.bot.delete_message.await_args_list]
        self.assertEqual(deleted, [17, 25])
        edit = self.bot.edit_message_text.await_args.kwargs
        self.assertEqual(edit["message_id"], 11)
        self.assertEqual(edit["reply_markup"], feed_keyboard(saved))

    async def test_old_reminder_is_confirmed_without_buttons(self):
        await self.add_user(pinned_message_id=11)
        self.bot.delete_message.side_effect = [TelegramBadRequest(
            method=DeleteMessage(chat_id=101, message_id=17),
            message="message can't be deleted",
        ), None]
        await self.take_pill(CB_PILL_TAKEN)
        self.bot.edit_message_text.assert_any_await(
            text=pill.CONFIRM_TEXT, chat_id=101, message_id=17, reply_markup=None
        )

    async def test_menu_status_uses_local_day_and_isolates_users(self):
        user = await self.add_user(pill_taken_date=date(2026, 9, 24))
        other = await self.add_user(102)
        with patch("bot.services.time_utils.datetime", wraps=datetime) as clock:
            # Уже следующий день в Москве, хотя в UTC ещё 24 сентября.
            clock.now.return_value = datetime(2026, 9, 24, 21, 5, tzinfo=timezone.utc)
            for person, expected in [(user, "💊 Таблетки"), (other, "💊 Таблетки")]:
                buttons = [b for row in feed_keyboard(person).inline_keyboard for b in row]
                self.assertNotIn(CB_STATS, [b.callback_data for b in buttons])
                self.assertEqual(next(b.text for b in buttons if b.callback_data == CB_PILL_MENU), expected)
            user.pill_taken_date = local_today(user)
            self.assertEqual(feed_keyboard(user).inline_keyboard[1][0].text, "✅ Выпил")
            clock.now.return_value += timedelta(days=1)
            self.assertEqual(feed_keyboard(user).inline_keyboard[1][0].text, "💊 Таблетки")

    async def test_repeated_confirmation_keeps_same_daily_status(self):
        user = await self.add_user(pinned_message_id=11)
        await self.take_pill(CB_PILL_MENU)
        self.bot.reset_mock()
        saved = await self.take_pill(CB_PILL_MENU)
        self.assertEqual(saved.id, user.id)
        self.bot.delete_message.assert_awaited_once_with(chat_id=101, message_id=25)

    async def test_blocked_user_does_not_interrupt_sending(self):
        user = await self.add_user()
        self.bot.send_message.side_effect = TelegramForbiddenError(
            method=SendMessage(chat_id=101, text=pill.PROMPT_TEXT),
            message="bot was blocked by the user",
        )
        await pill.send_daily_prompt(self.bot, user)


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_database_is_upgraded_and_preferences_survive_restart(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(engine.dispose)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY, telegram_id BIGINT UNIQUE NOT NULL,
                    pinned_message_id INTEGER, timezone VARCHAR(64) NOT NULL,
                    prompt_time VARCHAR(5), prompt_enabled BOOLEAN,
                    created_at DATETIME NOT NULL
                )
            """))
            await conn.execute(text("""
                INSERT INTO users (id, telegram_id, timezone, prompt_time, prompt_enabled, created_at)
                VALUES (1, 101, 'Europe/Moscow', '22:15', 0, '2026-09-23 12:00:00')
            """))
        with patch.object(db_session, "engine", engine):
            await db_session.init_db()
            async with factory() as session:
                user = await crud.get_user(session, 101)
                self.assertEqual(user.prompt_time, "22:15")
                self.assertFalse(user.prompt_enabled)
                self.assertEqual(user.pill_prompt_time, "20:00")
                self.assertTrue(user.pill_prompt_enabled)
                self.assertIsNone(user.pill_taken_date)
                await crud.set_pill_taken_date(session, user, date(2026, 9, 25))
                await crud.set_pill_prompt_time(session, user, "08:30")
                await crud.set_pill_prompt_enabled(session, user, False)
            await db_session.init_db()
            async with factory() as session:
                user = await crud.get_user(session, 101)
                self.assertEqual(user.pill_taken_date, date(2026, 9, 25))
                self.assertEqual(user.pill_prompt_time, "08:30")
                self.assertFalse(user.pill_prompt_enabled)
                self.assertEqual(user.prompt_time, "22:15")
                self.assertFalse(user.prompt_enabled)


if __name__ == "__main__":
    unittest.main()
