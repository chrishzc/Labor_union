"""
File: controlled_files.py
Description: 保留受控檔案舊 public entry 的穩定退役邊界。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.admin_auth import require_persisted_admin
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/storage", tags=["Controlled Files"])

_REPLACEMENT_IDENTIFIER = (
    "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService"
)
_REMOVAL_GATE = "blocked_media_successor_schema_and_runtime_gate"


def _raise_controlled_file_route_retired(route_identity: str) -> NoReturn:
    """Reject the legacy public route without invoking workflow or storage code."""

    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": {
                "category": "not_found",
                "code": "controlled_file_public_route_retired",
                "message": "受控檔案舊入口已退役，請等待受控 reference/finalize successor 完成切換。",
                "field_errors": [],
                "domain_blockers": [
                    f"replacement_identifier:{_REPLACEMENT_IDENTIFIER}",
                    f"removal_gate:{_REMOVAL_GATE}",
                ],
                "retryable": False,
                "correlation_id": f"controlled-files-retired:{route_identity}",
                "current_version": None,
            }
        },
    )


@router.post("/staging", response_model=None)
def stage_controlled_file(
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal
    _raise_controlled_file_route_retired("POST /api/v1/storage/staging")


@router.post("/files/preview", response_model=None)
def preview_controlled_file(
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal
    _raise_controlled_file_route_retired("POST /api/v1/storage/files/preview")


@router.post("/files/apply", response_model=None)
def apply_controlled_file(
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal
    _raise_controlled_file_route_retired("POST /api/v1/storage/files/apply")


@router.get("/files", response_model=None)
def list_controlled_files(
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal
    _raise_controlled_file_route_retired("GET /api/v1/storage/files")


@router.get("/files/{file_id}", response_model=None)
def get_controlled_file(
    file_id: str,
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal, file_id
    _raise_controlled_file_route_retired("GET /api/v1/storage/files/{file_id}")


@router.get("/files/{file_id}/download", response_model=None)
def download_controlled_file(
    file_id: str,
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal, file_id
    _raise_controlled_file_route_retired(
        "GET /api/v1/storage/files/{file_id}/download"
    )


@router.get("/receipts/{receipt_id}", response_model=None)
def get_controlled_file_receipt(
    receipt_id: str,
    principal: AdminPrincipal = Depends(require_persisted_admin),
) -> NoReturn:
    del principal, receipt_id
    _raise_controlled_file_route_retired(
        "GET /api/v1/storage/receipts/{receipt_id}"
    )


__all__ = [
    "router",
]
