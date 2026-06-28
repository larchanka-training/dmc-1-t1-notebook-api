# Notebook API — FastAPI Backend

FastAPI backend для JavaScript Notebook платформы. Предоставляет REST API для работы с notebook'ами, управления пользователями, AI-генерации кода и сбора аналитики.

## Возможности

- Versioned API routing (`/api/v1`)
- JWT-авторизация через HttpOnly cookies (register, login, logout, refresh, me)
- Async SQLAlchemy ORM с PostgreSQL (asyncpg)
- Alembic миграции
- Health check endpoint с детальной информацией
- AI генерация кода через AWS Bedrock с валидацией и ремонтом вывода
- Usage Analytics — трекинг событий и dashboard
- Структурированное JSON-логирование с trace context
- Конфигурация через Pydantic Settings
- Тесты на Pytest (unit + mocked-DB integration)

## Структура проекта

```
.
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app
│   ├── ai
│   │   ├── bedrock.py       # AWS Bedrock client (Converse API)
│   │   ├── context.py       # Сборка контекста notebook для LLM
│   │   ├── exceptions.py    # Иерархия исключений AI слоя
│   │   ├── prompt_guard.py  # Детекция prompt injection
│   │   ├── rate_limit.py    # Rate limiter per user (sliding window)
│   │   └── validation.py    # Извлечение кода + JS syntax validation
│   ├── api
│   │   └── v1
│   │       ├── endpoints
│   │       │   ├── ai.py         # /ai/generate, /ai/context, /ai/validate
│   │       │   ├── analytics.py  # /analytics/events, /analytics/dashboard
│   │       │   ├── auth.py       # /auth/register, /auth/login, /auth/refresh, ...
│   │       │   ├── health.py     # /health
│   │       │   └── notebooks.py  # CRUD notebooks
│   │       └── router.py
│   ├── core
│   │   ├── config.py        # Настройки через pydantic-settings
│   │   ├── logging_config.py # JSON логирование с trace context
│   │   ├── security.py      # JWT, password hashing
│   │   └── telemetry.py     # OpenTelemetry
│   ├── db
│   │   ├── base.py
│   │   ├── models
│   │   │   ├── analytics.py    # AnalyticsEvent
│   │   │   ├── notebook.py     # Notebook
│   │   │   ├── session.py      # Session
│   │   │   └── user.py         # User
│   │   └── session.py
│   ├── schemas
│   │   ├── ai.py
│   │   ├── analytics.py
│   │   ├── auth.py
│   │   └── notebook.py
│   ├── utils
│   │   └── tracing.py
│   └── main.py
├── tests/
├── alembic.ini
├── .env.example
├── pyproject.toml
└── requirements-dev.txt
```

## Быстрый старт

1. Создать виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Установить зависимости:

```bash
pip install -r requirements-dev.txt
```

3. Скопировать env-файл:

```bash
cp .env.example .env
```

4. Запустить приложение:

```bash
uvicorn app.main:app --reload
```

API документация:

- `http://127.0.0.1:8000/docs` — Swagger UI
- `http://127.0.0.1:8000/redoc` — ReDoc

## Команды

```bash
uvicorn app.main:app --reload   # Dev server на http://localhost:8000
ruff check .                    # Линтинг (политика нулевых ошибок)
pytest                          # Запуск всех тестов
alembic upgrade head            # Применить миграции БД
alembic revision --autogenerate -m "описание"  # Создать новую миграцию
```

## API

Базовый путь: `/api/v1`

| Endpoint                          | Методы                    | Описание                          |
|-----------------------------------|---------------------------|-----------------------------------|
| `/auth`                           | POST, GET, DELETE         | Регистрация, вход, logout, refresh |
| `/notebooks`                      | GET, POST, PUT, DELETE    | CRUD notebooks                    |
| `/ai/generate`                    | POST                      | Генерация JS кода через Bedrock   |
| `/ai/context`                     | POST                      | Сборка контекста для LLM          |
| `/ai/validate`                    | POST                      | Валидация вывода LLM              |
| `/analytics/events`               | POST                      | Запись события аналитики          |
| `/analytics/dashboard`            | GET                       | Dashboard со статистикой          |
| `/health`                         | GET                       | Health check                      |

## Логирование

Структурированное JSON-логирование с trace context:

- **Формат:** JSON с полями `timestamp`, `level`, `service`, `name`, `message`, `trace_id`, `user_id`
- **Уровни:** Настраиваются через env (`LOG_LEVEL`, `LOG_LEVEL_CONSOLE`, `LOG_LEVEL_FILE`)
- **Ротация:** Ежедневно в полночь, ~14 дней хранения
- **Trace context:** Каждая запись включает `trace_id` для трекинга запросов

```python
import logging

logger = logging.getLogger(__name__)

logger.info("User action completed", extra={"user_id": 123})
logger.error("Something went wrong", exc_info=True)
```

Конфигурация в `.env`:

```env
LOG_LEVEL=DEBUG
LOG_LEVEL_CONSOLE=DEBUG
LOG_LEVEL_FILE=INFO
LOG_FILE=logs/app.log
```

## AI генерация кода

`POST /api/v1/ai/generate` — генерация JavaScript из prompt через AWS Bedrock. Требует авторизации.

**Полный флоу:** собрать prompt через `/ai/context` → отправить в `/ai/generate` → получить валидированный JS.

| Проверка             | Лимит                                   | HTTP |
|----------------------|-----------------------------------------|------|
| Авторизация          | JWT required                            | 401  |
| Размер prompt        | `AI_MAX_PROMPT_CHARS` (default 32 000)  | 400  |
| Prompt injection     | 10 паттернов детекции                   | 400  |
| Rate limit (per user)| `AI_RATE_LIMIT_RPM` / `AI_RATE_LIMIT_RPD` | 429 |
| Ремонт синтаксиса    | до 3 попыток с обратной связью          | 422  |

Конфигурация Bedrock (env vars):

| Variable             | Default                  | Описание                    |
|----------------------|--------------------------|-----------------------------|
| `BEDROCK_MODEL_ID`   | `amazon.nova-lite-v1:0`  | Foundation model            |
| `BEDROCK_REGION`     | `eu-north-1`             | AWS регион                  |
| `AI_RATE_LIMIT_RPM`  | `10`                     | Max запросов в минуту       |
| `AI_RATE_LIMIT_RPD`  | `100`                    | Max запросов в день         |
| `AI_MAX_PROMPT_CHARS`| `32000`                  | Max длина prompt (символы)  |

В ECS credentials берутся из task IAM role. Локально — `~/.aws/credentials` или `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

См. [`docs/architecture/ai-generation.md`](../docs/architecture/ai-generation.md).

## AI валидация вывода

`POST /api/v1/ai/validate` — валидация raw LLM response перед показом в Code Cell: извлекает JS из произвольного вывода (markdown fences, prose) и проверяет синтаксис.

Syntax checking: [`esprima`](https://pypi.org/project/esprima/) (pure-Python, ES2017) + structural fallback. Repair loop (`app.ai.generate_validated_code`) пере-промптит LLM с текстом ошибки.

См. [`docs/architecture/ai-output-validation.md`](../docs/architecture/ai-output-validation.md).

## Usage Analytics

- `POST /api/v1/analytics/events` — запись события (`notebook_created`, `cell_executed`, `ai_request`, `execution_error`)
- `GET /api/v1/analytics/dashboard` — агрегированная статистика (total events, events by type, recent events)

## Как расширять

- Новые endpoints в `app/api/v1/endpoints/`, подключить в `app/api/v1/router.py`
- Новые ORM модели в `app/db/models/`, зарегистрировать в `app/db/models/__init__.py`
- Миграция: `alembic revision --autogenerate -m "описание изменения"`
- Бизнес-логика в новых модулях (например: `app/services/`)

