import logging

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging

logger = logging.getLogger(__name__)

setup_logging()

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"message": "Welcome to MSD FastAPI Template"}
