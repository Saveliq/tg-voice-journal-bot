"""Конфигурация приложения через pydantic-settings (.env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки бота, читаются из .env / переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./diary.db"

    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Время ежедневного вопроса о головной боли по умолчанию (HH:MM, в UTC).
    # Используется для новых пользователей; каждый может изменить в настройках.
    headache_prompt_time: str = "20:00"

    # Telegram id администратора — доступ к /testprompt
    admin_id: int = 780994100

    # Часовой пояс по умолчанию (IANA) для новых пользователей.
    # Каждый может изменить свой в настройках.
    default_tz: str = "Europe/Moscow"

    # Прокси для доступа к api.telegram.org (нужен при блокировке Telegram).
    # Форматы: http://host:port  или  socks5://user:pass@host:port
    proxy_url: str = ""

    log_level: str = "INFO"


settings = Settings()
