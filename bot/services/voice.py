"""Скачивание и транскрибация голосовых сообщений через faster-whisper.

Модель грузится ОДИН раз (ленивый singleton) — на слабом железе повторная
инициализация на каждое сообщение недопустимо медленная.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
from pathlib import Path

from aiogram import Bot

from bot.config import settings

_MODELS_DIR = Path(__file__).parent.parent.parent / "models"

logger = logging.getLogger(__name__)

_model = None  # type: ignore[var-annotated]
_model_lock = asyncio.Lock()

_MODEL_SIZES_MB = {
    "tiny": 75, "base": 145, "small": 490,
    "medium": 1500, "large": 2900, "large-v2": 2900, "large-v3": 2900,
}


def _local_model_path() -> Path | None:
    path = _MODELS_DIR / settings.whisper_model_size
    if path.exists() and any(path.iterdir()):
        return path
    return None


def _is_hf_cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        repo_id = f"Systran/faster-whisper-{settings.whisper_model_size}"
        result = try_to_load_from_cache(repo_id, "model.bin")
        return result is not None and isinstance(result, str)
    except Exception:
        return False


def _log_progress(stop_event: threading.Event) -> None:
    elapsed = 0
    while not stop_event.wait(10):
        elapsed += 10
        logger.info("Скачивание модели Whisper... %d сек", elapsed)


def _load_model():
    """Синхронная загрузка модели (вызывается в executor)."""
    from faster_whisper import WhisperModel

    local = _local_model_path()

    if local:
        logger.info("Загружаю Whisper из локальной папки: %s", local)
        model_path = str(local)
        stop_event = None
    elif _is_hf_cached():
        logger.info(
            "Загружаю Whisper из кеша HuggingFace: size=%s device=%s compute=%s",
            settings.whisper_model_size,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        model_path = settings.whisper_model_size
        stop_event = None
    else:
        size_mb = _MODEL_SIZES_MB.get(settings.whisper_model_size, "?")
        logger.info(
            "Модель Whisper-%s не найдена локально — скачиваю (~%s МБ). "
            "Это может занять несколько минут...",
            settings.whisper_model_size,
            size_mb,
        )
        model_path = settings.whisper_model_size
        stop_event = threading.Event()
        threading.Thread(target=_log_progress, args=(stop_event,), daemon=True).start()

    try:
        model = WhisperModel(
            model_path,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    finally:
        if stop_event is not None:
            stop_event.set()

    if stop_event is not None:
        logger.info("Модель Whisper успешно скачана и загружена.")

    return model


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
