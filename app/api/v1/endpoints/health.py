import logging

from fastapi import APIRouter

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    """Health check endpoint.

    Returns service status, name, environment, and API version.
    """
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "api_version": "v1",
    }
