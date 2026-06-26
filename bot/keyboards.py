"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# callback_data константы — используются и при построении, и при фильтрации
CB_FEED = "feed"
CB_STATS = "stats"
CB_EXPORT = "export"
CB_EXPORT_TXT = "export:txt"
CB_EXPORT_CSV = "export:csv"
CB_EXPORT_JSON = "export:json"


def feed_keyboard() -> InlineKeyboardMarkup:
    """Главное меню под лентой."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data=CB_STATS))
    kb.row(InlineKeyboardButton(text="📤 Экспорт", callback_data=CB_EXPORT))
    return kb.as_markup()


def stats_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Назад к ленте", callback_data=CB_FEED))
    return kb.as_markup()


def export_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="TXT", callback_data=CB_EXPORT_TXT),
        InlineKeyboardButton(text="CSV", callback_data=CB_EXPORT_CSV),
        InlineKeyboardButton(text="JSON", callback_data=CB_EXPORT_JSON),
    )
    kb.row(InlineKeyboardButton(text="⬅️ Назад к ленте", callback_data=CB_FEED))
    return kb.as_markup()
