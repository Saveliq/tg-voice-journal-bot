"""Работа со временем с учётом часового пояса пользователя.

«Сутки» и время напоминаний считаются в локальном поясе пользователя
(User.timezone, IANA-имя, например 'Europe/Moscow'). Записи в БД (created_at)
хранятся в naive-UTC, поэтому для выборок за «локальный день» переводим
границы локального дня в UTC.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_tz(name: str | None) -> ZoneInfo:
    """ZoneInfo по имени, с откатом на UTC при ошибке."""
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def user_tz(user) -> ZoneInfo:
    return get_tz(getattr(user, "timezone", "UTC") or "UTC")


def local_now(user) -> datetime:
    """Текущее время в поясе пользователя (aware)."""
    return datetime.now(timezone.utc).astimezone(user_tz(user))


def local_today(user) -> date:
    return local_now(user).date()


def _to_naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def day_bounds_utc(user, d: date) -> tuple[datetime, datetime]:
    """Границы [start, end) локального дня d в naive-UTC (для запросов по created_at)."""
    tz = user_tz(user)
    start_local = datetime(d.year, d.month, d.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return _to_naive_utc(start_local), _to_naive_utc(end_local)


def today_bounds_utc(user) -> tuple[datetime, datetime]:
    """Границы локального «сегодня» в naive-UTC."""
    return day_bounds_utc(user, local_today(user))
