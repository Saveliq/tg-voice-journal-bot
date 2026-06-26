"""Регистрация всех роутеров бота."""
from __future__ import annotations

from aiogram import Dispatcher

from bot.handlers import common, entries, menu, start


def register_handlers(dp: Dispatcher) -> None:
    # Порядок важен: команды и callbacks раньше «catch-all» в common.
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(entries.router)
    dp.include_router(common.router)
