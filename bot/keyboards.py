"""Inline-клавиатуры бота."""
from __future__ import annotations

import calendar as _calendar
from datetime import date, timedelta

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
CB_SET_TZ = "set:tz"

# Календарь. Режим в callback задаёт поведение тапа по дате:
#   cal:open              — открыть календарь-отчёт (текущий месяц)
#   cal:pickopen          — открыть календарь для выбора даты записи
#   cal:nav:<mode>:<YM>   — навигация по месяцам (mode = view | pick)
#   cal:day:<ISO-date>    — тап по дате в режиме view (popup)
#   cal:noop              — неактивная кнопка (заголовок/паддинг)
# (в режиме pick тап по дате использует hd:pick:<ISO> — см. ниже)
CB_CALENDAR = "cal:open"
CB_CAL_PICKOPEN = "cal:pickopen"
CB_CAL_NOOP = "cal:noop"
CAL_MODE_VIEW = "view"
CAL_MODE_PICK = "pick"

# --- Дневник головной боли ---
# Схема callback_data (разделитель ':'):
#   hd:start                       — ручной запуск: показать выбор даты
#   hd:pick:<ISO-date>             — выбрана дата записи → начать опрос
#   hd:had:1:<ISO-date>            — болела голова (да)
#   hd:had:0:<ISO-date>            — не болела (нет)
#   hd:pk:1:<entry_id>             — принимал обезболивающее (да)
#   hd:pk:0:<entry_id>             — не принимал (нет)
#   hd:med:<entry_id>:<med_id>     — выбран препарат из списка
#   hd:newmed:<entry_id>           — ввести новый препарат
CB_HD_START = "hd:start"
CB_HD_PREFIX = "hd:"

# Короткие названия дней/месяцев для кнопок выбора даты
_WD_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
_MON_GEN = ("янв", "фев", "мар", "апр", "мая", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек")


def _date_btn_label(d: date) -> str:
    return f"{_WD_SHORT[d.weekday()]} {d.day} {_MON_GEN[d.month - 1]}"


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


def headache_date_picker_keyboard(today: date) -> InlineKeyboardMarkup:
    """Выбор даты записи: сегодня, завтра, ещё 7 дней и календарь."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="Сегодня", callback_data=f"hd:pick:{today.isoformat()}"
        ),
        InlineKeyboardButton(
            text="Завтра",
            callback_data=f"hd:pick:{(today + timedelta(days=1)).isoformat()}",
        ),
    )
    # следующие 7 дней — по 2 в ряд
    days = [today + timedelta(days=i) for i in range(2, 9)]
    for i in range(0, len(days), 2):
        row = [
            InlineKeyboardButton(
                text=_date_btn_label(d), callback_data=f"hd:pick:{d.isoformat()}"
            )
            for d in days[i:i + 2]
        ]
        kb.row(*row)
    kb.row(
        InlineKeyboardButton(text="📅 Календарь", callback_data=CB_CAL_PICKOPEN)
    )
    kb.row(InlineKeyboardButton(text="⬅️ Назад к ленте", callback_data=CB_FEED))
    return kb.as_markup()


def calendar_keyboard(
    year: int, month: int, symbols: dict[int, str], mode: str = CAL_MODE_VIEW
) -> InlineKeyboardMarkup:
    """Календарь-сетка: заголовок месяца, дни с символами, навигация.

    mode=view — тап по дате открывает popup с записями дня;
    mode=pick — тап по дате начинает новую запись на эту дату (hd:pick:<ISO>).
    Визуально оба режима идентичны.
    """
    from bot.services.calendar_view import month_label, next_month, prev_month

    is_pick = mode == CAL_MODE_PICK
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
                cb = f"hd:pick:{iso}" if is_pick else f"cal:day:{iso}"
                row.append(
                    InlineKeyboardButton(text=f"{day}{sym}", callback_data=cb)
                )
        kb.row(*row)
    # Навигация по месяцам + возврат
    py, pm = prev_month(year, month)
    ny, nm = next_month(year, month)
    back_text = "⬅️ Назад" if is_pick else "📋 Лента"
    back_cb = CB_HD_START if is_pick else CB_FEED
    kb.row(
        InlineKeyboardButton(text="◀️", callback_data=f"cal:nav:{mode}:{py:04d}-{pm:02d}"),
        InlineKeyboardButton(text=back_text, callback_data=back_cb),
        InlineKeyboardButton(text="▶️", callback_data=f"cal:nav:{mode}:{ny:04d}-{nm:02d}"),
    )
    return kb.as_markup()


def settings_keyboard(prompt_enabled: bool) -> InlineKeyboardMarkup:
    """Меню настроек напоминания."""
    toggle_text = "🔕 Выключить напоминание" if prompt_enabled else "🔔 Включить напоминание"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🕐 Изменить время", callback_data=CB_SET_TIME))
    kb.row(InlineKeyboardButton(text="🌍 Часовой пояс", callback_data=CB_SET_TZ))
    kb.row(InlineKeyboardButton(text=toggle_text, callback_data=CB_SET_TOGGLE))
    kb.row(InlineKeyboardButton(text="⬅️ Назад к ленте", callback_data=CB_FEED))
    return kb.as_markup()


# Часовые пояса для выбора (метка, IANA-имя)
TIMEZONES = [
    ("UTC+2 Калининград", "Europe/Kaliningrad"),
    ("UTC+3 Москва", "Europe/Moscow"),
    ("UTC+4 Самара", "Europe/Samara"),
    ("UTC+5 Екатеринбург", "Asia/Yekaterinburg"),
    ("UTC+6 Омск", "Asia/Omsk"),
    ("UTC+7 Красноярск", "Asia/Krasnoyarsk"),
    ("UTC+8 Иркутск", "Asia/Irkutsk"),
    ("UTC+9 Якутск", "Asia/Yakutsk"),
    ("UTC+10 Владивосток", "Asia/Vladivostok"),
    ("UTC+11 Магадан", "Asia/Magadan"),
    ("UTC+12 Камчатка", "Asia/Kamchatka"),
    ("UTC+0 (UTC)", "UTC"),
]


def timezone_keyboard() -> InlineKeyboardMarkup:
    """Список часовых поясов (по 2 в ряд)."""
    kb = InlineKeyboardBuilder()
    for i in range(0, len(TIMEZONES), 2):
        row = [
            InlineKeyboardButton(text=label, callback_data=f"tz:set:{iana}")
            for label, iana in TIMEZONES[i:i + 2]
        ]
        kb.row(*row)
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_SETTINGS))
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
