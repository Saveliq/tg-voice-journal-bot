"""Календарь головной боли: подсчёт символов по дням и статистики за месяц."""
from __future__ import annotations

import calendar as _calendar
import html
from collections import Counter, defaultdict
from datetime import date

from bot.db.models import HeadacheEntry

_MONTHS_NOM = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

# Символы на кнопке дня
SYM_HEADACHE = "🔸"   # болела голова
SYM_MED = "🔺"        # принимал препарат
SYM_MARK = "✓"        # была отметка (ответил, но не болела)


def month_label(year: int, month: int) -> str:
    return f"{_MONTHS_NOM[month - 1]} {year}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def month_range(year: int, month: int) -> tuple[date, date]:
    last_day = _calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _group_by_day(entries: list[HeadacheEntry]) -> dict[date, list[HeadacheEntry]]:
    groups: dict[date, list[HeadacheEntry]] = defaultdict(list)
    for e in entries:
        groups[e.entry_date].append(e)
    return groups


def day_symbols(entries: list[HeadacheEntry]) -> dict[int, str]:
    """Один взаимоисключающий символ на день: {номер_дня: 'символ'}.

    Приоритет (от старшего к младшему):
        🔺 принимал препарат (подразумевает боль)
        🔸 болела голова без препарата
        ✓  ответил, но голова не болела
    """
    result: dict[int, str] = {}
    for day, day_entries in _group_by_day(entries).items():
        had = any(e.had_headache for e in day_entries)
        med = any(e.medication_id is not None or e.took_painkiller for e in day_entries)
        if med:
            result[day.day] = SYM_MED
        elif had:
            result[day.day] = SYM_HEADACHE
        else:
            result[day.day] = SYM_MARK
    return result


def _count_streaks(headache_days: list[date], min_len: int = 3) -> int:
    """Число серий подряд идущих дней с болью длиной >= min_len."""
    if not headache_days:
        return 0
    days = sorted(set(headache_days))
    streaks = 0
    run = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            run += 1
        else:
            if run >= min_len:
                streaks += 1
            run = 1
    if run >= min_len:
        streaks += 1
    return streaks


def month_stats_text(year: int, month: int, entries: list[HeadacheEntry]) -> str:
    """Текст-сводка под календарём (в формате из ТЗ)."""
    headache_entries = [e for e in entries if e.had_headache]
    intakes = [e for e in headache_entries if e.took_painkiller]
    med_counter: Counter[str] = Counter(
        e.medication.name for e in entries if e.medication is not None
    )
    headache_days = [e.entry_date for e in headache_entries]
    long_streaks = _count_streaks(headache_days, min_len=3)

    lines = [
        "<b>Ваш дневник</b>",
        "",
        html.escape(month_label(year, month)),
        f"🔸 Головные боли — {len(headache_entries)}",
        f"🔺 Приёмы препаратов — {len(intakes)}",
    ]
    if med_counter:
        lines.append("💊 В дневнике:")
        for name, cnt in med_counter.most_common():
            lines.append(f"{html.escape(name)} — {cnt}")
    lines.append(f"🤕 Болела больше 2 дней подряд — {long_streaks}")
    return "\n".join(lines)


def day_popup_text(entries: list[HeadacheEntry], day: date) -> str:
    """Короткий текст для всплывающего окна при тапе на дату."""
    from bot.services.headache import format_headache_feed_line

    same_day = [e for e in entries if e.entry_date == day]
    if not same_day:
        return f"{day.isoformat()}: записей нет"
    lines = [format_headache_feed_line(e, escape=False) for e in same_day]
    return f"{day.isoformat()}\n" + "\n".join(lines)
