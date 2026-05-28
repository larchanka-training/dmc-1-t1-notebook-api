# Skill: Добавить новый endpoint

Добавить новый REST endpoint в FastAPI backend по образцу существующего `api/v1/endpoints/health.py`.

## Шаги

### 1. Создать файл endpoint

```
app/api/v1/endpoints/<resource>.py
```

```python
from fastapi import APIRouter

router = APIRouter(prefix="/<resource>", tags=["<resource>"])

@router.get("/")
async def list_items():
    return []
```

### 2. Зарегистрировать router

Открыть `app/api/v1/router.py` и подключить новый router:

```python
from app.api.v1.endpoints.<resource> import router as <resource>_router

api_router.include_router(<resource>_router)
```

### 3. Написать pytest тест

Создать `tests/test_<resource>.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_list_items():
    response = client.get("/api/v1/<resource>/")
    assert response.status_code == 200
```

## Верификация

```bash
ruff check .   # должен пройти без ошибок
pytest         # должен пройти
```
