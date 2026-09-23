"""Скачивает модели Whisper в папку ./models/ для офлайн-использования."""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

MODELS = [
    ("tiny",   "Systran/faster-whisper-tiny",   75),
    ("base",   "Systran/faster-whisper-base",   145),
    ("small",  "Systran/faster-whisper-small",  490),
    ("medium", "Systran/faster-whisper-medium", 1500),
]

MODELS_DIR = Path(__file__).parent / "models"


def download(name: str, repo_id: str, size_mb: int) -> None:
    from huggingface_hub import snapshot_download

    dest = MODELS_DIR / name
    if dest.exists() and any(dest.iterdir()):
        logger.info("[%s] уже скачана — пропускаю", name)
        return

    logger.info("[%s] Скачиваю ~%d МБ из %s...", name, size_mb, repo_id)
    snapshot_download(repo_id=repo_id, local_dir=str(dest))
    logger.info("[%s] Готово -> %s", name, dest)


def main() -> None:
    MODELS_DIR.mkdir(exist_ok=True)

    targets = sys.argv[1:] if sys.argv[1:] else [m[0] for m in MODELS]
    selected = [m for m in MODELS if m[0] in targets]

    if not selected:
        logger.error("Неизвестные модели: %s. Доступны: %s", targets, [m[0] for m in MODELS])
        sys.exit(1)

    total_mb = sum(m[2] for m in selected)
    logger.info("Будет скачано: %s (~%d МБ суммарно)", [m[0] for m in selected], total_mb)

    for name, repo_id, size_mb in selected:
        download(name, repo_id, size_mb)

    logger.info("Все модели готовы в %s", MODELS_DIR)


if __name__ == "__main__":
    main()
