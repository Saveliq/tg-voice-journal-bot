# tg-voice-journal-bot

Личный дневник в Telegram «одним сообщением». Пользователь пишет текст или
присылает голосовое — запись попадает в базу с временной меткой. У бота
**всегда ровно одно «живое» сообщение** в чате: оно редактируется и показывает
ленту записей за сегодня. Любой ввод пользователя удаляется сразу после
обработки — в чате видна только лента.

## Напоминания

Ежедневно бот присылает вопрос о головной боли и отдельное сообщение
«выпил таблетку ?» с единственной кнопкой «Да». Нажатие «Да» подтверждает
приём и убирает напоминание; дополнительного опроса и записи в дневник нет.
Если Telegram не разрешает удалить старое сообщение, оно заменяется
подтверждением без кнопок.

В **⚙️ Настройки → 🕐 Время: таблетка** можно задать время в формате `ЧЧ:ММ`.
У каждого напоминания своё время и переключатель включения. Оба используют
выбранный часовой пояс. Напоминание о таблетке включено по умолчанию на 20:00;
для новых пользователей время по умолчанию задаёт `PILL_PROMPT_TIME`.
При запуске бота необходимые колонки добавляются в существующую базу автоматически.

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
| `HEADACHE_PROMPT_TIME` | время вопроса о головной боли для новых пользователей (по умолчанию `20:00`) |
| `PILL_PROMPT_TIME` | время напоминания о таблетке для новых пользователей (по умолчанию `20:00`) |
| `DEFAULT_TZ` | часовой пояс новых пользователей (по умолчанию `Europe/Moscow`) |
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
- **Локальное время пользователя** (см. `services/time_utils`) используется
  для «сегодня» и обоих напоминаний; даты записей хранятся в UTC.

## Проверки

```bash
python -m unittest discover -s tests -v
```

Тесты используют SQLite в памяти и не обращаются к Telegram или рабочей базе.

## Деплой (позже)

`Dockerfile` + `docker-compose.yml` поднимают сервисы `bot` и `db` (Postgres).
Для prod достаточно переключить `DATABASE_URL` на
`postgresql+asyncpg://…` — код менять не нужно.
