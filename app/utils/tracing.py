"""Контекст трассировки для структурных логов.

`trace_id` — короткий идентификатор, уникальный на одно внешнее действие.
Привязывается к текущему `asyncio.Task` через `contextvars.ContextVar`;
логгинг-фильтр автоматически прокидывает его в каждую JSON-запись лога.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any

from opentelemetry import trace as otel_trace

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
user_id_var: ContextVar[Any] = ContextVar("user_id", default=None)


def new_trace_id() -> str:
    """Сгенерировать новый короткий `trace_id` (12 hex-символов)."""
    return uuid.uuid4().hex[:12]


def bind_trace_id(value: str | None) -> Token[str | None]:
    """Привязать `trace_id` к текущему контексту.

    Возвращает токен для последующего `reset_trace_id`.
    """
    return trace_id_var.set(value)


def get_trace_id() -> str | None:
    """Return active OTel trace ID when valid, else trace_id_var, else None."""
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return trace_id_var.get()


def reset_trace_id(token: Token[str | None]) -> None:
    """Сбросить `trace_id` по токену от `bind_trace_id`."""
    trace_id_var.reset(token)


def bind_user_id(value: Any) -> Token[Any]:
    """Привязать `user_id` к текущему контексту."""
    return user_id_var.set(value)


def get_user_id() -> Any:
    """Получить текущий `user_id` из контекста (или `None`)."""
    return user_id_var.get()


def reset_user_id(token: Token[Any]) -> None:
    """Сбросить `user_id` по токену от `bind_user_id`."""
    user_id_var.reset(token)
