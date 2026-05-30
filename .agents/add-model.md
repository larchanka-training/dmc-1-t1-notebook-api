# Skill: Добавить SQLAlchemy модель + Alembic миграцию

Пошаговый гайд для добавления новой таблицы в БД: модель → миграция → dependency → тест.

Репо использует PostgreSQL (connection string в `DATABASE_URL`). `app/db/` создаётся
впервые по этому гайду, если её ещё не существует.

---

## Шаг 1 — Установить зависимости

Добавить в `requirements.txt`:

```
sqlalchemy>=2.0
alembic>=1.13
asyncpg>=0.29        # async PostgreSQL driver
psycopg2-binary>=2.9 # sync driver (нужен alembic autogenerate)
```

Установить:

```bash
pip install -r requirements-dev.txt
```

---

## Шаг 2 — Создать базовую структуру app/db/ (только первый раз)

```
app/db/
├── __init__.py
├── base.py       # DeclarativeBase
├── session.py    # engine + AsyncSession factory + get_db dependency
└── models/
    └── __init__.py
```

**`app/db/base.py`:**

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

**`app/db/session.py`:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

---

## Шаг 3 — Создать модель

Создать файл `app/db/models/<resource>.py`:

```python
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Resource(Base):
    __tablename__ = "<resources>"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

Зарегистрировать в `app/db/models/__init__.py`:

```python
from app.db.models.<resource> import Resource  # noqa: F401
```

---

## Шаг 4 — Инициализировать Alembic (только первый раз)

```bash
alembic init -t async alembic
```

Обновить `alembic/env.py` — подключить модели и engine:

```python
from app.db.base import Base
from app.db.models import *  # noqa: F401, F403 — регистрирует все модели
from app.core.config import settings

# В run_migrations_online():
connectable = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
)
target_metadata = Base.metadata
```

---

## Шаг 5 — Создать миграцию и применить локально

```bash
alembic revision --autogenerate -m "add <resource> table"
```

Просмотреть сгенерированный файл в `alembic/versions/` и убедиться что он корректен.

Применить к **локальной** БД:

```bash
alembic upgrade head
```

> **Важно:** `alembic upgrade head` вручную запускается **только локально**.
> Dev и prod RDS находятся в приватных подсетях AWS — прямое подключение
> с ноутбука к ним невозможно. Миграции на AWS применяются автоматически
> при старте контейнера (см. следующий шаг).

---

## Шаг 6 — Обновить Dockerfile для автоматических миграций на AWS

RDS в dev и prod окружениях недоступен напрямую (приватная подсеть, нет VPN/bastion).
Миграции применяются автоматически: при каждом деплое ECS запускает новый контейнер,
который сначала выполняет `alembic upgrade head`, затем стартует сервер.

Обновить `CMD` в `Dockerfile`:

```dockerfile
# Было:
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]

# Стало:
CMD ["sh", "-c", "alembic upgrade head && fastapi run app/main.py --host 0.0.0.0 --port 8000"]
```

`DATABASE_URL` уже инжектируется из AWS Secrets Manager в ECS task definition —
Alembic получает его автоматически через `settings.database_url`.

Alembic использует блокировку на уровне БД, поэтому одновременный запуск двух
контейнеров во время rolling update безопасен — второй просто дождётся первого.

---

## Шаг 7 — Использовать в endpoint

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

router = APIRouter(prefix="/<resources>", tags=["<resources>"])

@router.get("/")
async def list_resources(db: AsyncSession = Depends(get_db)):
    ...
```

---

## Шаг 8 — Написать тест

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_list_resources():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/<resources>/")
    assert response.status_code == 200
```

---

## Верификация

```bash
ruff check .   # нулевых ошибок
pytest         # все тесты зелёные
alembic heads  # одна голова, без расхождений
```
