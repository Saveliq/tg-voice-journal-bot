"""Работа со временем и границами «сегодня».

ВАЖНО (зафиксированное решение): «сегодня» считается по UTC.
Локальный день пользователя пока не учитывается — поле users.timezone
зарезервировано на будущее. Это сделано осознанно, чтобы избежать
путаницы в логике и не вводить переключатели дат на старте.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone


def _naive_utc(dt: datetime) -> datetime:
    """Привести к naive-UTC (в БД даты хранятся без tz-инфо)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def today_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Вернуть [начало_сегодня, начало_завтра) в naive-UTC."""
    now = now or datetime.now(timezone.utc)
    now = _naive_utc(now)
    start = datetime.combine(now.date(), time.min)
    end = start + timedelta(days=1)
    return start, end


def day_bounds(day_date) -> tuple[datetime, datetime]:
    """Границы [start, end) конкретной даты (date) в naive-UTC."""
    start = datetime.combine(day_date, time.min)
    end = start + timedelta(days=1)
    return start, end
