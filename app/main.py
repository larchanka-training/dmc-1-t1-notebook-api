import logging

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.telemetry import setup_telemetry

logger = logging.getLogger(__name__)

setup_logging()
setup_telemetry()

app = FastAPI(title=settings.app_name)
FastAPIInstrumentor.instrument_app(app)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"message": "Welcome to MSD FastAPI Template"}
