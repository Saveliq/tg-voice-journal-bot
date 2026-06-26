"""Скачивание и транскрибация голосовых сообщений через faster-whisper.

Модель грузится ОДИН раз (ленивый singleton) — на слабом железе повторная
инициализация на каждое сообщение недопустимо медленная.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from aiogram import Bot

from bot.config import settings

logger = logging.getLogger(__name__)

_model = None  # type: ignore[var-annotated]
_model_lock = asyncio.Lock()


def _load_model():
    """Синхронная загрузка модели (вызывается в executor)."""
    from faster_whisper import WhisperModel

    logger.info(
        "Загружаю Whisper: size=%s device=%s compute=%s",
        settings.whisper_model_size,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    return WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


async def get_model():
    """Ленивая инициализация singleton-модели (потокобезопасно для asyncio)."""
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                loop = asyncio.get_running_loop()
                _model = await loop.run_in_executor(None, _load_model)
    return _model


async def warmup_model() -> None:
    """Прогрев модели при старте приложения, чтобы первый запрос был быстрым."""
    await get_model()


def _transcribe_sync(model, audio_path: str) -> str:
    segments, _info = model.transcribe(audio_path, language="ru")
    return " ".join(seg.text.strip() for seg in segments).strip()


async def transcribe_voice(bot: Bot, file_id: str) -> str:
    """Скачать .ogg по file_id, транскрибировать, вернуть текст.

    Возвращает пустую строку, если распознать ничего не удалось.
    Временный файл удаляется в finally.
    """
    model = await get_model()

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    audio_path = tmp.name
    tmp.close()

    try:
        await bot.download(file_id, destination=audio_path)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            None, _transcribe_sync, model, audio_path
        )
        return text
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            logger.warning("Не удалось удалить временный файл %s", audio_path)
