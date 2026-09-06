"""Authenticated Staff six-relation manual Query/Preview/Apply routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path

from api.dependencies.admin_auth import admin_actor_context, require_admin
from api.dependencies.staff_case_preference_manual import StaffCasePreferenceManualApplication, get_staff_case_preference_manual_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_case_preference_manual import ManualApplyBody, ManualReceiptView, ManualSnapshotView, RelationsBody
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.case_preference_manual_workflow import CasePreferenceManualApplyRequest

router = APIRouter(prefix="/api/v1/staff/case-preference-manual", tags=["Staff Case Preference Manual"])


@router.get("/{staff_id}", response_model=BaseResponse[ManualSnapshotView])
def query_manual_preferences(
    staff_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffCasePreferenceManualApplication = Depends(get_staff_case_preference_manual_application),
):
    del principal
    try:
        snapshot = application.workflow.query(staff_id)
        return BaseResponse(data=_snapshot_payload(snapshot), message="成功取得六大接案能力")
    except ValueError as error:
        _raise(error)


@router.post("/{staff_id}/preview", response_model=BaseResponse[ManualSnapshotView])
def preview_manual_preferences(
    body: RelationsBody,
    staff_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffCasePreferenceManualApplication = Depends(get_staff_case_preference_manual_application),
):
    del principal
    try:
        preview = application.workflow.preview(staff_id, body.as_relations())
        return BaseResponse(data={
            "staff_id": preview.staff_id,
            "before": _relations_payload(preview.before),
            "after": _relations_payload(preview.after),
            "snapshot_fingerprint": preview.snapshot_fingerprint.value,
            "preview_fingerprint": preview.preview_fingerprint.value,
        }, message="成功產生六大接案能力預覽")
    except ValueError as error:
        _raise(error)


@router.post("/{staff_id}/apply", response_model=BaseResponse[ManualReceiptView])
def apply_manual_preferences(
    body: ManualApplyBody,
    staff_id: int = Path(..., gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffCasePreferenceManualApplication = Depends(get_staff_case_preference_manual_application),
):
    request = CasePreferenceManualApplyRequest(
        PreviewFingerprint(body.expected_snapshot_fingerprint),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        admin_actor_context(principal),
        body.reason.strip(),
        CorrelationId(correlation_id),
    )
    try:
        receipt = application.workflow.apply(staff_id, body.as_relations(), request)
        return BaseResponse(data=_receipt_payload(receipt), message="六大接案能力已套用")
    except ValueError as error:
        _raise(error, correlation_id)


def _snapshot_payload(snapshot):
    relations = _relations_payload(snapshot.relations)
    return {
        "staff_id": snapshot.staff_id,
        "before": relations,
        "after": relations,
        "snapshot_fingerprint": snapshot.snapshot_fingerprint.value,
        "preview_fingerprint": None,
    }


def _relations_payload(relations):
    return {
        key: [{"value": item.value, "detail": item.detail} for item in values]
        for key, values in relations.items()
    }


def _receipt_payload(receipt):
    return {
        "staff_id": receipt.staff_id,
        "relations": _relations_payload(receipt.relations),
        "snapshot_fingerprint": receipt.snapshot_fingerprint.value,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "idempotency_key": receipt.idempotency_key.value,
        "replayed": receipt.replayed,
    }


def _raise(error, correlation: str | None = None):
    code = str(error) or "staff_case_preference_manual_invalid"
    if code == "staff_not_found":
        status, category = 404, "not_found"
    elif code.endswith("stale_snapshot") or code.endswith("stale_preview") or code.endswith("idempotency_conflict"):
        status, category = 409, "conflict"
    else:
        status, category = 422, "validation"
    raise typed_http_error(status, category, code, code, correlation or uuid4().hex)


__all__ = ["router"]
