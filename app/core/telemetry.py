"""Инициализация OpenTelemetry: трейсы и логи через OTLP gRPC."""
import logging

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings


def setup_telemetry() -> None:
    """Настроить TracerProvider и LoggerProvider с OTLP-экспортом.

    Вызывать до создания FastAPI-приложения. Если OTEL_ENABLED=false — no-op.
    """
    if not settings.otel_enabled:
        return

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})

    # --- Трейсы ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
    )
    trace.set_tracer_provider(tracer_provider)

    # --- Логи ---
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=settings.otel_endpoint))
    )
    set_logger_provider(logger_provider)

    # Мост: Python logging → OTel (все logger.info/error/... идут в Aspire)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))
