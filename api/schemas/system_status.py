from datetime import datetime

from pydantic import BaseModel, Field


class PerformanceSnapshotResponse(BaseModel):
    started_at: datetime
    request_count: int = Field(ge=0)
    average_response_time_ms: float | None = Field(default=None, ge=0)
    p50_response_time_upper_bound_ms: int | None = Field(default=None, ge=0)
    p95_response_time_upper_bound_ms: int | None = Field(default=None, ge=0)
    maximum_response_time_ms: float | None = Field(default=None, ge=0)
