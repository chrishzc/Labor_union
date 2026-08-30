"""
File: line_admin.py
Description: 定義 LINE 管理中心 capability projection 的封閉公開 schema。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LineAdminFeatureFlagsView(_ClosedModel):
    health_overview: bool
    message_template_api: bool
    message_schedule_api: bool
    message_schedule_editor: bool
    line_task_admin_api: bool
    line_task_attempt_history: bool
    rich_menu_api: bool
    rich_menu_editor: bool
    rich_menu_publication_history: bool
    liff_config_api: bool
    liff_config_editor: bool
    liff_runtime_config: bool
    liff_revision_history: bool
    customer_service_config_api: bool
    staff_review_api: bool
    staff_review_management: bool
    admin_session: bool
    role_permissions: bool
    audit_log: bool
    order_group_management: bool
    contract_evidence: bool
    knowledge_management: bool


class LineAdminRuntimeAvailabilityView(_ClosedModel):
    line_worker_enabled: bool
    contract_worker_enabled: bool
    knowledge_worker_enabled: bool


class LineAdminConfigFilesView(_ClosedModel):
    message_templates: bool
    message_schedules: bool
    line_menus: bool
    liff: bool
    customer_service: bool


class LineAdminCapabilitiesView(_ClosedModel):
    stage: Literal["9"]
    effective_capabilities: list[str]
    features: LineAdminFeatureFlagsView
    runtime_availability: LineAdminRuntimeAvailabilityView
    config_files: LineAdminConfigFilesView


class LineWorkerHealthView(_ClosedModel):
    status: Literal[
        "healthy", "stale", "missing", "degraded", "stopped", "unknown"
    ]
    running: bool
    worker_identity: str | None = None
    runtime_mode: Literal["legacy", "canonical", "compatibility"] | None = None
    heartbeat_age_seconds: float | None = None
    last_error_code: str | None = None


class LegacyLineTaskCountsView(_ClosedModel):
    pending: int = Field(default=0, ge=0)
    processing: int = Field(default=0, ge=0)
    sent: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)


class LineQueueCountsView(_ClosedModel):
    inbox_pending: int = Field(default=0, ge=0)
    delivery_pending: int = Field(default=0, ge=0)
    legacy_pending: int = Field(default=0, ge=0)
    matching_delivery_active: int = Field(default=0, ge=0)
    matching_delivery_failed: int = Field(default=0, ge=0)


class LineDatabaseHealthView(_ClosedModel):
    ok: bool
    line_task_counts: LegacyLineTaskCountsView
    queue_counts: LineQueueCountsView
    worker: LineWorkerHealthView
    error_code: Literal["line_database_unavailable"] | None = None


class LineCredentialPresenceView(_ClosedModel):
    channel_secret: bool
    channel_access_token: bool
    liff_id: bool


class LineAdminHealthView(_ClosedModel):
    status: Literal["healthy", "degraded"]
    database: LineDatabaseHealthView
    worker: LineWorkerHealthView
    line_credentials: LineCredentialPresenceView


__all__ = [
    "LineAdminCapabilitiesView",
    "LineAdminConfigFilesView",
    "LineAdminHealthView",
    "LineCredentialPresenceView",
    "LineDatabaseHealthView",
    "LineAdminFeatureFlagsView",
    "LineQueueCountsView",
    "LineAdminRuntimeAvailabilityView",
    "LineWorkerHealthView",
    "LegacyLineTaskCountsView",
]
