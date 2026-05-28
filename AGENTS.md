# AGENTS.md — dmc-1-t1-notebook-api

FastAPI backend для JavaScript Notebook платформы. Предоставляет REST API для работы с данными notebook, управления пользователями и выполнения ячеек.

## Tech Stack

- **Runtime:** Python 3.11
- **Framework:** FastAPI + Uvicorn
- **Валидация:** Pydantic + pydantic-settings
- **Тестирование:** pytest
- **Линтинг:** ruff (line-length 88, правила: E, F, I)

## Структура папок

```
app/
├── api/
│   └── v1/
│       ├── endpoints/   # Один файл на ресурс (например health.py)
│       └── router.py    # Объединяет все endpoint роутеры
├── core/
│   ├── config.py        # Настройки через pydantic-settings
│   ├── logging_config.py
│   └── telemetry.py     # Настройка OpenTelemetry
├── utils/
│   └── tracing.py
└── main.py              # FastAPI app factory, подключает api_router
tests/
└── test_health.py       # pytest тесты
```

## CLI команды

```bash
uvicorn app.main:app --reload   # Dev server на http://localhost:8000
ruff check .                    # Линтинг (политика нулевых ошибок)
pytest                          # Запуск всех тестов
```

## API

Базовый путь: `/api/v1`
Интерактивная документация: `http://localhost:8000/docs`

## Task Skills

Пошаговые гайды в папке `.agents/`:
- [`add-endpoint.md`](.agents/add-endpoint.md) — добавить новый FastAPI endpoint

## Agent Workflow

### 1. Перед выполнением задачи
- Изучи задачу, подготовь план, предоставь пользователю на ревью
- Получи явное одобрение перед началом любых изменений в коде

### 2. Git (после одобрения плана)
```bash
git checkout main
git pull origin main
git checkout -b <тип>/<краткое-описание>   # feat/, fix/, chore/
```

### 3. Тестирование
- Покрыть изменения pytest тестами (моки через `unittest.mock` где нужно)
- Каждый новый endpoint требует минимум одного теста

### 4. Перед коммитом
- Запроси одобрение у пользователя с кратким summary изменений
- После одобрения запусти тесты — все должны пройти:
```bash
ruff check .
pytest
```

### 5. Формат коммита
```
<Тема: максимум 50 символов>

# Краткое описание
* Что реализовано

# Почему
* Причины выбора подхода

# План тестирования
✅ pytest: X/X пройдены (включая N новых)
```

### 6. Pull Request
```bash
gh pr create --title "<заголовок до 70 символов>" --body "..."
```
Тело PR: краткий Summary + Test plan.
