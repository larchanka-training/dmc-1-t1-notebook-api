# FastAPI Template (MSD Course)

A simple, extensible FastAPI starter template for students in the Modern Software Development course.

## What is included

- FastAPI app with versioned API routing
- JWT-based authentication via HttpOnly cookies (register, login, logout, refresh, me)
- Async SQLAlchemy ORM with PostgreSQL (asyncpg)
- Alembic migrations
- Health check endpoint with detailed service information
- AI output validation & repair pipeline (extract code, JS syntax check, retry)
- Structured JSON logging system with trace context
- Environment-based configuration with Pydantic Settings
- Test setup with Pytest (unit + mocked-DB integration tests)
- Clear folder structure for future growth

## Project structure

```text
.
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app
│   ├── ai
│   │   ├── bedrock.py       # AWS Bedrock client (Converse API)
│   │   ├── context.py       # Notebook context builder for LLM prompts
│   │   ├── exceptions.py    # AI layer exception hierarchy
│   │   ├── prompt_guard.py  # Prompt injection detection
│   │   ├── rate_limit.py    # Per-user sliding-window rate limiter
│   │   └── validation.py    # LLM output extraction + JS syntax validation
│   ├── api
│   │   └── v1
│   │       ├── endpoints
│   │       │   ├── ai.py        # /ai/generate, /ai/context, /ai/validate
│   │       │   ├── auth.py
│   │       │   ├── health.py
│   │       │   └── notebooks.py
│   │       └── router.py
│   ├── core
│   │   ├── config.py
│   │   ├── logging_config.py
│   │   └── security.py
│   ├── db
│   │   ├── base.py
│   │   ├── models
│   │   │   ├── session.py
│   │   │   └── user.py
│   │   └── session.py
│   ├── schemas
│   │   ├── ai.py
│   │   └── auth.py
│   ├── utils
│   │   └── tracing.py
│   └── main.py
├── tests/
├── alembic.ini
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
- Add new ORM models in `app/db/models/` and register them in `app/db/models/__init__.py`
- Generate a migration after model changes: `alembic revision --autogenerate -m "describe the change"`
- Add business logic/services in new modules (for example: `app/services/`)

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

## AI Code Generation

`POST /api/v1/ai/generate` — generates JavaScript code from a prompt via AWS Bedrock. Requires authentication.

**Full flow:** build a prompt with `/ai/context` → send it to `/ai/generate` → receive validated, executable JS.

Request:

```json
{ "prompt": "<text from POST /ai/context>" }
```

Response:

```json
{
  "code": "const x = [1, 2, 3].map(n => n * 2);\nconsole.log(x);",
  "language": "javascript",
  "isValid": true,
  "attempts": 1
}
```

**Safeguards:**

| Check | Limit | HTTP |
|-------|-------|------|
| Auth | JWT required | 401 |
| Prompt size | `AI_MAX_PROMPT_CHARS` (default 32 000) | 400 |
| Injection patterns | 10 common patterns detected | 400 |
| Rate limit (per user) | `AI_RATE_LIMIT_RPM` / `AI_RATE_LIMIT_RPD` | 429 |
| Syntax repair | up to 3 attempts, error fed back to model | 422 if all fail |

See [`docs/architecture/ai-generation.md`](../docs/architecture/ai-generation.md) for full detail.

**Bedrock configuration** (env vars):

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` | Foundation model to use |
| `BEDROCK_REGION` | `eu-north-1` | AWS region for Bedrock calls |
| `AI_RATE_LIMIT_RPM` | `10` | Max requests per minute per user |
| `AI_RATE_LIMIT_RPD` | `100` | Max requests per day per user |
| `AI_MAX_PROMPT_CHARS` | `32000` | Max prompt length in characters |

In ECS, credentials come from the task IAM role automatically. Locally, configure `~/.aws/credentials` or set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

---

## AI Output Validation

`POST /api/v1/ai/validate` validates a raw LLM response before it is shown in a
Code Cell: it extracts executable JavaScript from arbitrary model output
(markdown fences, prose, no fences) and checks its syntax.

Request:

```json
{ "raw": "Sure!\n```js\nconst x = 1;\nconsole.log(x);\n```" }
```

Response:

```json
{
  "isValid": true,
  "code": "const x = 1;\nconsole.log(x);",
  "language": "javascript",
  "reason": "ok",
  "issues": [],
  "validator": "esprima"
}
```

Syntax checking uses [`esprima`](https://pypi.org/project/esprima/) (pure-Python,
ES2017) with a dependency-free structural fallback. The repair loop
(`app.ai.generate_validated_code`) re-prompts the LLM with the error text on
invalid output. See `docs/architecture/ai-output-validation.md`.

