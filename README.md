# tg-voice-journal-bot

Личный дневник в Telegram «одним сообщением». Пользователь пишет текст или
присылает голосовое — запись попадает в базу с временной меткой. У бота
**всегда ровно одно «живое» сообщение** в чате: оно редактируется и показывает
ленту записей за сегодня. Любой ввод пользователя удаляется сразу после
обработки — в чате видна только лента.

## Стек

- Python 3.11+
- [aiogram 3.x](https://docs.aiogram.dev/) — Telegram-фреймворк (async)
- SQLAlchemy 2.0 (async ORM) + `aiosqlite` (dev) / `asyncpg` (prod)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — локальная транскрибация голоса (CPU)
- pydantic-settings — конфиг из `.env`

## Установка (dev)

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # и заполнить BOT_TOKEN
```

> Для транскрибации голосовых нужен установленный **ffmpeg** в PATH.

## Запуск

```bash
python -m bot.main
```

При первом запуске создаётся SQLite-файл `diary.db` (через `create_all`) и
прогревается Whisper-модель.

## Конфигурация (`.env`)

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен бота от @BotFather |
| `DATABASE_URL` | строка подключения SQLAlchemy (dev: SQLite, prod: Postgres) |
| `WHISPER_MODEL_SIZE` | размер модели Whisper (`base`/`small`/…) |
| `WHISPER_DEVICE` | `cpu` или `cuda` |
| `WHISPER_COMPUTE_TYPE` | напр. `int8` (быстро на CPU) |
| `LOG_LEVEL` | уровень логирования |

## Структура

```
bot/
├── main.py                # точка входа, polling
├── config.py              # pydantic-settings
├── keyboards.py           # inline-клавиатуры
├── handlers/              # start, entries, menu, common
├── services/              # singleton_message, feed, voice, stats, export, time_utils
└── db/                    # models, session, crud
```

## Архитектурные решения

- **«Единственное сообщение»** — вся логика отправки/редактирования главного
  сообщения сосредоточена в `services/singleton_message.safe_edit_or_recreate`.
  Хендлеры не вызывают `send_message`/`edit_message_text` для UI напрямую.
- **Конкурентность** — обработка сообщений одного пользователя сериализуется
  per-user `asyncio.Lock`, чтобы параллельные правки одного сообщения не
  конфликтовали.
- **«Сегодня» считается по UTC** (см. `services/time_utils`). Локальный день
  пользователя пока не учитывается — поле `users.timezone` зарезервировано.

## Деплой (позже)

`Dockerfile` + `docker-compose.yml` поднимают сервисы `bot` и `db` (Postgres).
Для prod достаточно переключить `DATABASE_URL` на
`postgresql+asyncpg://…` — код менять не нужно.
