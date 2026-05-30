import logging

import psycopg2
from fastapi import APIRouter, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    """Health check endpoint.

    Returns service status, name, environment, and API version.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "api_version": "v1",
    }


@router.get("/health/db")
def healthcheck_db() -> dict[str, str]:
    """Database connectivity health check.

    Attempts a real connection to verify the database is reachable.
    Returns 503 if the database is unavailable.
    """
    if not settings.database_url:
        return {"status": "not_configured", "detail": "DATABASE_URL is not set"}

    try:
        conn = psycopg2.connect(settings.database_url, connect_timeout=5)
        conn.close()
        return {"status": "healthy", "detail": "database connection successful"}
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
