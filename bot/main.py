"""Точка входа: запуск бота в режиме long polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.session import init_db
from bot.handlers import register_handlers
from bot.services.voice import warmup_model

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


async def main() -> None:
    setup_logging()

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан. Заполни .env (см. .env.example).")

    logger.info("Инициализация БД...")
    await init_db()

    session = AiohttpSession(proxy=settings.proxy_url or None)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()
    register_handlers(dp)

    # Грузим Whisper заранее, чтобы первое голосовое не ждало инициализацию.
    logger.info("Прогрев Whisper-модели...")
    try:
        await warmup_model()
    except Exception:  # noqa: BLE001 — бот должен стартовать даже без модели
        logger.exception("Не удалось загрузить Whisper-модель при старте")

    logger.info("Бот запущен. Начинаю polling.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
