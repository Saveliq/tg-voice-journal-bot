"""Регистрация всех роутеров бота."""
from __future__ import annotations

from aiogram import Dispatcher

from bot.handlers import (
    admin,
    calendar,
    common,
    entries,
    headache,
    menu,
    settings,
    start,
)


def register_handlers(dp: Dispatcher) -> None:
    # Порядок важен: команды и callbacks раньше «catch-all» в common.
    # headache/settings раньше entries — чтобы FSM-ввод (препарат/время)
    # перехватывал текст до того, как его подхватит обработчик записей.
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(headache.router)
    dp.include_router(calendar.router)
    dp.include_router(settings.router)
    dp.include_router(menu.router)
    dp.include_router(entries.router)
    dp.include_router(common.router)
