"""Inline-клавиатуры бота."""
from __future__ import annotations

import calendar as _calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import Medication

# callback_data константы — используются и при построении, и при фильтрации
CB_FEED = "feed"
CB_STATS = "stats"
CB_EXPORT = "export"
CB_EXPORT_TXT = "export:txt"
CB_EXPORT_CSV = "export:csv"
CB_EXPORT_JSON = "export:json"

# Настройки
CB_SETTINGS = "settings"
CB_SET_TIME = "set:time"
CB_SET_TOGGLE = "set:toggle"

# Календарь
#   cal:open              — открыть календарь (текущий месяц)
#   cal:nav:<YYYY-MM>     — перейти к месяцу
#   cal:day:<ISO-date>    — тап по дате (popup)
#   cal:noop              — неактивная кнопка (заголовок/паддинг)
CB_CALENDAR = "cal:open"
CB_CAL_NOOP = "cal:noop"

# --- Дневник головной боли ---
# Схема callback_data (разделитель ':'):
#   hd:start                       — ручной запуск опроса за сегодня
#   hd:had:1:<ISO-date>            — болела голова (да)
#   hd:had:0:<ISO-date>            — не болела (нет)
#   hd:pk:1:<entry_id>             — принимал обезболивающее (да)
#   hd:pk:0:<entry_id>             — не принимал (нет)
#   hd:med:<entry_id>:<med_id>     — выбран препарат из списка
#   hd:newmed:<entry_id>           — ввести новый препарат
CB_HD_START = "hd:start"
CB_HD_PREFIX = "hd:"


def feed_keyboard() -> InlineKeyboardMarkup:
    """Главное меню под лентой."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🤕 Голова", callback_data=CB_HD_START),
        InlineKeyboardButton(text="📅 Календарь", callback_data=CB_CALENDAR),
    )
    kb.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data=CB_STATS),
        InlineKeyboardButton(text="📤 Экспорт", callback_data=CB_EXPORT),
    )
    kb.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data=CB_SETTINGS))
    return kb.as_markup()


def calendar_keyboard(
    year: int, month: int, symbols: dict[int, str]
) -> InlineKeyboardMarkup:
    """Календарь-сетка: заголовок месяца, дни с символами, навигация."""
    from bot.services.calendar_view import month_label, next_month, prev_month

    kb = InlineKeyboardBuilder()
    # Заголовок «Месяц Год»
    kb.row(
        InlineKeyboardButton(
            text=month_label(year, month), callback_data=CB_CAL_NOOP
        )
    )
    # Шапка дней недели
    kb.row(
        *[
            InlineKeyboardButton(text=w, callback_data=CB_CAL_NOOP)
            for w in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        ]
    )
    # Недели месяца (0 — день из соседнего месяца → пустая кнопка)
    cal = _calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=CB_CAL_NOOP))
            else:
                sym = symbols.get(day, "")
                iso = date(year, month, day).isoformat()
                row.append(
                    InlineKeyboardButton(
                        text=f"{day}{sym}", callback_data=f"cal:day:{iso}"
                    )
                )
        kb.row(*row)
    # Навигация по месяцам + возврат к ленте
    py, pm = prev_month(year, month)
    ny, nm = next_month(year, month)
    kb.row(
        InlineKeyboardButton(text="◀️", callback_data=f"cal:nav:{py:04d}-{pm:02d}"),
        InlineKeyboardButton(text="📋 Лента", callback_data=CB_FEED),
        InlineKeyboardButton(text="▶️", callback_data=f"cal:nav:{ny:04d}-{nm:02d}"),
    )
    return kb.as_markup()


def settings_keyboard(prompt_enabled: bool) -> InlineKeyboardMarkup:
    """Меню настроек напоминания."""
    toggle_text = "🔕 Выключить напоминание" if prompt_enabled else "🔔 Включить напоминание"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🕐 Изменить время", callback_data=CB_SET_TIME))
    kb.row(InlineKeyboardButton(text=toggle_text, callback_data=CB_SET_TOGGLE))
    kb.row(InlineKeyboardButton(text="⬅️ Назад к ленте", callback_data=CB_FEED))
    return kb.as_markup()


def headache_ask_keyboard(entry_date: date) -> InlineKeyboardMarkup:
    """«Болела голова?» — да/нет, дата зашита в callback."""
    iso = entry_date.isoformat()
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Да", callback_data=f"hd:had:1:{iso}"),
        InlineKeyboardButton(text="Нет", callback_data=f"hd:had:0:{iso}"),
    )
    return kb.as_markup()


def painkiller_ask_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    """«Принимали обезболивающие?» — да/нет."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Да", callback_data=f"hd:pk:1:{entry_id}"),
        InlineKeyboardButton(text="Нет", callback_data=f"hd:pk:0:{entry_id}"),
    )
    return kb.as_markup()


def medication_keyboard(
    entry_id: int, medications: list[Medication]
) -> InlineKeyboardMarkup:
    """Меню ранее введённых препаратов + ввод нового."""
    kb = InlineKeyboardBuilder()
    for med in medications:
        kb.row(
            InlineKeyboardButton(
                text=med.name, callback_data=f"hd:med:{entry_id}:{med.id}"
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="➕ Другой препарат", callback_data=f"hd:newmed:{entry_id}"
        )
    )
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
