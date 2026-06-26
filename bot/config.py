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

    # Прокси для доступа к api.telegram.org (нужен при блокировке Telegram).
    # Форматы: http://host:port  или  socks5://user:pass@host:port
    proxy_url: str = ""

    log_level: str = "INFO"


settings = Settings()
