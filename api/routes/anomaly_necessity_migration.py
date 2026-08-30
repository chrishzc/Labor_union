"""
File: anomaly_necessity_migration.py
Description: 保留舊 anomaly necessity migration public contract 的穩定退役邊界。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.admin_auth import require_persisted_admin
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(
    prefix="/api/v1/admin/anomaly-necessity-migration",
    tags=["Anomalies Maintenance"],
)

_ERROR_CODE = "anomaly_necessity_migration_retired"
_REMOVAL_GATE = "blocked_external_caller_evidence"
_QUERY_REPLACEMENT = "GET /api/v1/anomalies"
_ACTION_REPLACEMENT = (
    "owner_action_from:GET /api/v1/anomalies/{issue_key}/actions/{action_key}"
)


def _raise_retired(route_identity: str, replacement: str) -> NoReturn:
    """Reject the legacy entry without resolving a writer or opening a UoW."""

    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": {
                "category": "domain_blocked",
                "code": _ERROR_CODE,
                "message": (
                    "舊 anomaly necessity migration 已退役；請使用 current-only "
                    "anomaly projection 與 owner action。"
                ),
                "field_errors": [],
                "domain_blockers": [
                    f"replacement_identifier:{replacement}",
                    f"removal_gate:{_REMOVAL_GATE}",
                ],
                "retryable": False,
                "correlation_id": (
                    "anomaly-necessity-migration-retired:" + route_identity
                ),
                "current_version": None,
            }
        },
    )


@router.get("/alerts", response_model=None)
def query_anomaly_necessity_migration_alerts(
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal
    _raise_retired(
        "GET /api/v1/admin/anomaly-necessity-migration/alerts",
        _QUERY_REPLACEMENT,
    )


@router.post("/alerts/{alert_fingerprint}/preview", response_model=None)
def preview_anomaly_necessity_migration(
    alert_fingerprint: str,
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal, alert_fingerprint
    _raise_retired(
        "POST /api/v1/admin/anomaly-necessity-migration/alerts/"
        "{alert_fingerprint}/preview",
        _ACTION_REPLACEMENT,
    )


@router.post("/alerts/{alert_fingerprint}/apply", response_model=None)
def apply_anomaly_necessity_migration(
    alert_fingerprint: str,
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal, alert_fingerprint
    _raise_retired(
        "POST /api/v1/admin/anomaly-necessity-migration/alerts/"
        "{alert_fingerprint}/apply",
        _ACTION_REPLACEMENT,
    )


__all__ = ["router"]
