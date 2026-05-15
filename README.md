# FastAPI Template (MSD Course)

A simple, extensible FastAPI starter template for students in the Modern Software Development course.

## What is included

- FastAPI app with versioned API routing
- Health check endpoint with detailed service information
- Structured JSON logging system with trace context
- Environment-based configuration with Pydantic Settings
- Basic test setup with Pytest
- Clear folder structure for future growth

## Project structure

```text
.
├── app
│   ├── api
│   │   └── v1
│   │       ├── endpoints
│   │       │   └── health.py
│   │       └── router.py
│   ├── core
│   │   ├── config.py
│   │   └── logging_config.py
│   ├── utils
│   │   └── tracing.py
│   └── main.py
├── logs
│   └── app.log
├── tests
│   └── test_health.py
├── .env.example
├── pyproject.toml
└── requirements-dev.txt
```

## Quick start

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements-dev.txt
```

3. Copy env file:

```bash
cp .env.example .env
```

4. Run app:

```bash
uvicorn app.main:app --reload
```

API docs will be available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## Run tests

```bash
pytest
```

## How to extend

- Add new endpoints in `app/api/v1/endpoints/`
- Include endpoint routers inside `app/api/v1/router.py`
- Add business logic/services in new modules (for example: `app/services/`)
- Add database layer later (`app/db/`) when needed

## Logging

The application uses structured JSON logging with trace context:

- **Log format**: JSON with fields `timestamp`, `level`, `service`, `name`, `message`, `trace_id`, `user_id`
- **Log levels**: Configurable via environment variables (`LOG_LEVEL`, `LOG_LEVEL_CONSOLE`, `LOG_LEVEL_FILE`)
- **Log rotation**: Daily rotation at midnight with ~14-day retention (~2 weeks)
- **Trace context**: Each log entry includes a `trace_id` for request tracking

### Using the logger

```python
import logging

logger = logging.getLogger(__name__)

logger.info("User action completed", extra={"user_id": 123})
logger.error("Something went wrong", exc_info=True)
```

### Configuration

Add to your `.env` file:

```env
LOG_LEVEL=DEBUG
LOG_LEVEL_CONSOLE=DEBUG
LOG_LEVEL_FILE=INFO
LOG_FILE=logs/app.log
```

## Health Check

The health check endpoint is available at `/api/v1/health` and returns:

```json
{
  "status": "healthy",
  "service": "MSD FastAPI Template",
  "environment": "dev",
  "api_version": "v1"
}
```

This endpoint can be used by load balancers, orchestrators, or monitoring systems to verify service availability.

