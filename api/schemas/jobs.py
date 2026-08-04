from typing import Any, Literal

from pydantic import BaseModel, Field

class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    receipt_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    command_type: str | None = None
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    result_reference: str | None = None

class JobAcceptedResponse(BaseModel):
    job_id: str
    status_url: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
