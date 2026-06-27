"""SQLAlchemy 2.0 модели данных."""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Текущее время в UTC как naive datetime (без tz-инфо).

    Колонки объявлены TIMESTAMP WITHOUT TIME ZONE; Postgres/asyncpg не принимает
    timezone-aware значения в такие колонки. Весь код хранит и сравнивает даты
    в naive-UTC (см. services/time_utils), поэтому возвращаем naive.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class Base(DeclarativeBase):
    pass


class SourceType(str, enum.Enum):
    text = "text"
    voice = "voice"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # id текущего «единственного» сообщения бота в чате с этим пользователем
    pinned_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # на будущее — для локального «сегодня» пользователя; сейчас фиксируем UTC
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    # Персональное расписание ежедневного вопроса о ГБ (HH:MM в UTC)
    prompt_time: Mapped[str] = mapped_column(String(5), default="20:00")
    prompt_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    entries: Mapped[list["Entry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=16)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="entries")


class Medication(Base):
    """Справочник препаратов пользователя — для меню «ранее введённых вариантов»."""

    __tablename__ = "medications"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_medication"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HeadacheEntry(Base):
    """Запись дневника головной боли. На один день может быть несколько записей."""

    __tablename__ = "headache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # День, к которому привязана запись (важно: не дата нажатия кнопки)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    had_headache: Mapped[bool] = mapped_column(Boolean)
    took_painkiller: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    medication_id: Mapped[int | None] = mapped_column(
        ForeignKey("medications.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    medication: Mapped["Medication | None"] = relationship(lazy="joined")
