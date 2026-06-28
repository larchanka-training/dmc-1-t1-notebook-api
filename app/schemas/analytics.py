from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

EventType = Literal[
    "notebook_created",
    "cell_executed",
    "ai_request",
    "execution_error",
]


class AnalyticsEventCreate(BaseModel):
    event_type: EventType
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventResponse(BaseModel):
    id: UUID
    event_type: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def model_validate(cls, obj: Any) -> "AnalyticsEventResponse":  # type: ignore[override]
        return cls(
            id=obj.id,
            event_type=obj.event_type,
            metadata=obj.event_metadata,
            created_at=obj.created_at,
        )


class EventCountItem(BaseModel):
    event_type: str
    count: int


class DashboardResponse(BaseModel):
    total_events: int
    events_by_type: list[EventCountItem]
    recent_events: list[AnalyticsEventResponse]
