"""Typed transport contracts for authenticated private runtime operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkerRuntimeIdentity(BaseModel):
    service_name: str = Field(min_length=1, max_length=100)
    instance_id: str = Field(min_length=1, max_length=191)
    process_id: int = Field(ge=0)
    hostname: str = Field(min_length=1, max_length=191)
    started_at: datetime
    release_version: str = Field(min_length=1, max_length=100)


class DurableWorkerCycleRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)
    runtime_identity: WorkerRuntimeIdentity
    lease_seconds: int = Field(default=60, ge=5, le=3600)
    retry_delay_seconds: int = Field(default=15, ge=1, le=3600)
    check_only: bool = False


class WorkerCycleRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)
    runtime_identity: WorkerRuntimeIdentity


class RuntimeObservationInput(BaseModel):
    service_name: str = Field(min_length=1, max_length=100)
    component: str = Field(min_length=1, max_length=200)
    status: Literal["healthy", "warning", "critical", "unknown"]
    message: str = Field(max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    latency_ms: int | None = Field(default=None, ge=0)


class MonitorCycleRequest(BaseModel):
    runtime_identity: WorkerRuntimeIdentity
    observations: tuple[RuntimeObservationInput, ...] = Field(max_length=50)


class WorkerCycleResponse(BaseModel):
    processed: int = Field(ge=0)
    operation: str


class MonitorCycleResponse(BaseModel):
    observations_recorded: int = Field(ge=0)
    events_projected: int = Field(ge=0)


class RuntimeReadinessItem(BaseModel):
    check_name: str
    status: Literal["healthy", "warning", "critical", "unknown"]
    message: str


class RuntimeReadinessResponse(BaseModel):
    ready: bool
    checks: tuple[RuntimeReadinessItem, ...]


class ReactAdminArtifactHealthResponse(BaseModel):
    """Closed, redacted attestation for the mounted React admin artifact."""

    model_config = ConfigDict(extra="forbid", strict=True)

    active_selector: Literal["current", "previous"]
    artifact_version: str = Field(min_length=1, max_length=191)
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    api_compatibility_revision: str = Field(min_length=1, max_length=191)
    root_marker_checked: Literal[True]
    checked_asset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    healthy: Literal[True]
