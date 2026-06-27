import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user
from app.db.models.analytics import AnalyticsEvent
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.analytics import (
    AnalyticsEventCreate,
    AnalyticsEventResponse,
    DashboardResponse,
    EventCountItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events", response_model=AnalyticsEventResponse, status_code=201)
async def create_event(
    body: AnalyticsEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsEventResponse:
    event = AnalyticsEvent(
        user_id=current_user.id,
        event_type=body.event_type,
        event_metadata=body.metadata,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    logger.info(
        "Analytics event: user=%s type=%s",
        current_user.id,
        body.event_type,
    )
    return AnalyticsEventResponse.model_validate(event)


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    count_result = await db.execute(
        select(AnalyticsEvent.event_type, func.count())
        .where(AnalyticsEvent.user_id == current_user.id)
        .group_by(AnalyticsEvent.event_type)
    )
    counts = count_result.all()
    events_by_type = [
        EventCountItem(event_type=et, count=c) for et, c in counts
    ]
    total_events = sum(c for _, c in counts)

    recent_result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == current_user.id)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(limit)
    )
    recent = recent_result.scalars().all()
    recent_events = [AnalyticsEventResponse.model_validate(e) for e in recent]

    logger.info(
        "Analytics dashboard: user=%s total=%d",
        current_user.id,
        total_events,
    )
    return DashboardResponse(
        total_events=total_events,
        events_by_type=events_by_type,
        recent_events=recent_events,
    )
