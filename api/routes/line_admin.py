"""
================================================================================
檔案名稱: api/routes/line_admin.py
功能說明: LINE 管理中心總覽 API，提供系統健康狀態、Worker 狀態與管理功能清單
================================================================================
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from api.dependencies.admin_auth import require_line_viewer
from api.dependencies.line_runtime import get_line_database_health
from api.schemas.base import BaseResponse
from api.schemas.line_admin import (
    LineAdminCapabilitiesView,
    LineAdminConfigFilesView,
    LineAdminHealthView,
    LineCredentialPresenceView,
    LineDatabaseHealthView,
    LineAdminFeatureFlagsView,
    LineAdminRuntimeAvailabilityView,
)
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(
    prefix="/api/v1/line/admin",
    tags=["LINE Admin"],
    dependencies=[Depends(require_line_viewer)],
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_") and value != "mock_token")


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/health", response_model=BaseResponse[LineAdminHealthView])
def line_admin_health(
    database: LineDatabaseHealthView = Depends(get_line_database_health),
) -> BaseResponse[LineAdminHealthView]:
    worker = database.worker
    status_text = "healthy" if database.ok and worker.running else "degraded"
    return BaseResponse(
        data=LineAdminHealthView(
            status=status_text,
            database=database,
            worker=worker,
            line_credentials=LineCredentialPresenceView(
                channel_secret=_configured("LINE_CHANNEL_SECRET"),
                channel_access_token=_configured("LINE_CHANNEL_ACCESS_TOKEN"),
                liff_id=_configured("LINE_LIFF_ID"),
            ),
        )
    )


@router.get(
    "/capabilities",
    response_model=BaseResponse[LineAdminCapabilitiesView],
)
# Keep this projection together so operators can audit capability and feature drift in one response.
def line_admin_capabilities(
    principal: AdminPrincipal = Depends(require_line_viewer),
) -> BaseResponse[LineAdminCapabilitiesView]:
    return BaseResponse(
        data=LineAdminCapabilitiesView(
            stage="9",
            effective_capabilities=sorted(principal.effective_capabilities()),
            features=LineAdminFeatureFlagsView(
                health_overview=True,
                message_template_api=True,
                message_schedule_api=True,
                message_schedule_editor=True,
                line_task_admin_api=True,
                line_task_attempt_history=True,
                rich_menu_api=True,
                rich_menu_editor=True,
                rich_menu_publication_history=True,
                liff_config_api=True,
                liff_config_editor=True,
                liff_runtime_config=True,
                liff_revision_history=True,
                customer_service_config_api=True,
                staff_review_api=True,
                staff_review_management=True,
                admin_session=True,
                role_permissions=True,
                audit_log=True,
                order_group_management=True,
                contract_evidence=True,
                knowledge_management=True,
            ),
            runtime_availability=LineAdminRuntimeAvailabilityView(
                line_worker_enabled=True,
                contract_worker_enabled=_enabled(
                    "CONTRACT_INTEGRATION_RUNTIME_ENABLED"
                ),
                knowledge_worker_enabled=_enabled(
                    "KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED"
                ),
            ),
            config_files=LineAdminConfigFilesView(
                message_templates=(PROJECT_ROOT / "config/message_templates.json").exists(),
                message_schedules=(PROJECT_ROOT / "config/message_schedules.json").exists(),
                line_menus=(PROJECT_ROOT / "config/line_menu.json").exists(),
                liff=(PROJECT_ROOT / "config/liff_settings.json").exists(),
                customer_service=(PROJECT_ROOT / "config/customer_service.json").exists(),
            ),
        ),
    )
