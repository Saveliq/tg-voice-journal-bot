"""SQLAlchemy 2.0 модели данных."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Текущее время в UTC (без tz-инфо, секундная точность хранится в БД)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


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
