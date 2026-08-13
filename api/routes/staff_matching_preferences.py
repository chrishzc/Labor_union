"""Typed staff matching preference Query, Preview, and Apply endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_matching_preferences import (
    StaffMatchingPreferenceApplication,
    get_staff_matching_preference_application,
)
from api.schemas.base import BaseResponse
from api.schemas.staff_matching_preferences import (
    DefinitionApplyRequest,
    DefinitionPreviewRequest,
    DefinitionPreviewView,
    ProfileApplyRequest,
    ProfilePreviewView,
    StaffPreferenceApplyReceiptView,
    StaffPreferenceDefinitionView,
    StaffPreferenceProfileInput,
    StaffPreferenceProfileView,
)
from domains.scheduling.staff_matching_preferences import (
    PreferenceComparisonOperator,
    PreferenceValueKind,
    StaffPreferenceDefinition,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_matching_preference_workflow import PreferenceApplyRequest


router = APIRouter(
    prefix="/api/v1/scheduling/staff-matching-preferences",
    tags=["Scheduling Staff Matching Preferences"],
)


@router.get("/definitions", response_model=BaseResponse[list[StaffPreferenceDefinitionView]])
def query_definitions(
    include_inactive: bool = Query(default=False),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    del principal
    rows = application.workflow.query_definitions(active_only=not include_inactive)
    return BaseResponse(data=[_definition_view(item, version) for item, version in rows])


@router.post("/definitions/{preference_key}/preview", response_model=BaseResponse[DefinitionPreviewView])
def preview_definition(
    body: DefinitionPreviewRequest,
    preference_key: str = Path(min_length=1, max_length=64),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    del principal
    try:
        preview = application.workflow.preview_definition(_definition(preference_key, body.definition))
        return BaseResponse(data=_definition_preview_view(preview))
    except ValueError as error:
        _raise_preference_error(error)


@router.post("/definitions/{preference_key}/apply", response_model=BaseResponse[StaffPreferenceApplyReceiptView])
def apply_definition(
    body: DefinitionApplyRequest,
    preference_key: str = Path(min_length=1, max_length=64),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    request = _apply_request(body, idempotency_key, correlation_id, principal)
    try:
        result = application.workflow.apply_definition(_definition(preference_key, body.definition), request)
        return BaseResponse(data=result, message="月嫂偏好欄位已更新")
    except ValueError as error:
        _raise_preference_error(error)


@router.get("/staff/{staff_id}", response_model=BaseResponse[StaffPreferenceProfileView])
def query_profile(
    staff_id: int = Path(gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    del principal
    try:
        preview = application.workflow.query_profile(staff_id)
        return BaseResponse(data=_profile_view(preview.staff_id, preview.version, preview.after))
    except ValueError as error:
        _raise_preference_error(error)


@router.post("/staff/{staff_id}/preview", response_model=BaseResponse[ProfilePreviewView])
def preview_profile(
    body: StaffPreferenceProfileInput,
    staff_id: int = Path(gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    del principal
    try:
        preview = application.workflow.preview_profile(staff_id, _profile_values(body))
        return BaseResponse(data=_profile_preview_view(preview))
    except ValueError as error:
        _raise_preference_error(error)


@router.post("/staff/{staff_id}/apply", response_model=BaseResponse[StaffPreferenceApplyReceiptView])
def apply_profile(
    body: ProfileApplyRequest,
    staff_id: int = Path(gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffMatchingPreferenceApplication = Depends(get_staff_matching_preference_application),
):
    request = _apply_request(body, idempotency_key, correlation_id, principal)
    try:
        result = application.workflow.apply_profile(staff_id, _profile_values(body), request)
        return BaseResponse(data=_receipt_view(result), message="月嫂偏好已更新")
    except ValueError as error:
        _raise_preference_error(error)


def _definition(key, body):
    operator = None if body.comparison_operator is None else PreferenceComparisonOperator(body.comparison_operator)
    return StaffPreferenceDefinition(key, body.display_name.strip(), PreferenceValueKind(body.value_kind), body.is_filterable, body.order_fact_key, operator, body.active)


def _definition_view(definition, version):
    return {**definition.canonical_payload(), "version": version}


def _definition_preview_view(preview):
    return {
        "after": _definition_view(preview.after, preview.version),
        "before": None if preview.before is None else _definition_view(preview.before, preview.version),
        "preview_fingerprint": preview.fingerprint.value,
        "version": preview.version,
    }


def _profile_values(body):
    values: dict[str, dict[str, object]] = {}
    for item in body.values:
        if item.preference_key in values:
            raise HTTPException(status_code=422, detail="preference_key_duplicate")
        values[item.preference_key] = item.value.canonical_value()
    return values


def _profile_view(staff_id, version, values):
    return {"staff_id": staff_id, "values": _value_views(values), "version": version}


def _profile_preview_view(preview):
    return {
        "after": _value_views(preview.after),
        "before": _value_views(preview.before),
        "preview_fingerprint": preview.fingerprint.value,
        "staff_id": preview.staff_id,
        "version": preview.version,
    }


def _value_views(values):
    return [
        {"preference_key": key, "value": _typed_value(value)}
        for key, value in sorted(values.items())
    ]


def _typed_value(value):
    if "values" in value:
        return {"kind": "integer_set", "values": value["values"]}
    return {"kind": "integer_range", "maximum": value["maximum"], "minimum": value["minimum"]}


def _receipt_view(result):
    return {**result, "values": _value_views(result["values"])}


def _apply_request(body, key, correlation, principal):
    return PreferenceApplyRequest(
        ExpectedVersion(body.expected_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        CorrelationId(correlation),
    )


def _raise_preference_error(error):
    code = str(error)
    if code in {"staff_not_found", "preference_definition_not_found"}:
        status_code = 404
    elif code in {"stale_version", "stale_preview", "idempotency_conflict", "preference_semantics_immutable"}:
        status_code = 409
    else:
        status_code = 422
    raise HTTPException(status_code=status_code, detail={"code": code, "message": "月嫂偏好操作被拒絕。"}) from error
