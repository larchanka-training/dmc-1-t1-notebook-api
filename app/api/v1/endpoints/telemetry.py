import logging

from fastapi import APIRouter
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(tags=["telemetry"])


@router.get("/telemetry/ping")
def telemetry_ping() -> dict[str, str]:
    """Тестовый endpoint — генерирует span и лог для проверки Aspire Dashboard.

    Возвращает trace_id и span_id текущего OTel-спана.
    Если OTel выключен — возвращает нулевые идентификаторы (no-op span).
    """
    with tracer.start_as_current_span("telemetry.ping") as span:
        span.set_attribute("test.source", "telemetry_endpoint")
        logger.info("Telemetry ping called", extra={"endpoint": "/telemetry/ping"})
        ctx = span.get_span_context()
        return {
            "status": "ok",
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
