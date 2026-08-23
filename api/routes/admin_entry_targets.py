"""
File: admin_entry_targets.py
Description: 提供管理端 entry target 的唯讀查詢、零寫入 Preview 與單筆 CAS Apply API。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path as ApiPath, Request

from api.dependencies.admin_auth import require_admin
from api.schemas.admin_entry_targets import (
    ArtifactBindingView,
    EntryTargetCommandInput,
    EntryTargetPreviewView,
    EntryTargetReceiptView,
    EntryTargetStateView,
    EntryTargetView,
)
from api.schemas.base import BaseResponse
from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from subsystems.access.admin_entry_target_control import (
    AdminEntryTargetControl,
    ArtifactBinding,
    EntryTargetError,
    EntryTargetRecord,
    EntryTargetState,
    SwitchCommand,
    SwitchReceipt,
)
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/admin/entry-targets", tags=["Admin Entry Targets"])


def get_admin_entry_target_control(request: Request) -> AdminEntryTargetControl:
    raw_path = os.getenv("ADMIN_ENTRY_TARGET_STATE_PATH")
    if not raw_path:
        _raise_error(
            EntryTargetError("unavailable", "entry_target_state_path_missing", "Entry target state path 未設定"),
            _correlation(request),
        )
    try:
        return AdminEntryTargetControl(FileAdminEntryTargetStore(Path(raw_path)))
    except EntryTargetError as error:
        _raise_error(error, _correlation(request))


@router.get("", response_model=BaseResponse[EntryTargetStateView])
def query_entry_targets(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),
    control: AdminEntryTargetControl = Depends(get_admin_entry_target_control),
):
    del principal
    try:
        return BaseResponse(data=_state_view(control.query()))
    except EntryTargetError as error:
        _raise_error(error, _correlation(request))


@router.get("/{entry_id}", response_model=BaseResponse[EntryTargetView])
def resolve_entry_target(
    request: Request,
    entry_id: str = ApiPath(pattern=r"^ui-react:#[a-z0-9-]+$", max_length=191),
    principal: AdminPrincipal = Depends(require_admin),
    control: AdminEntryTargetControl = Depends(get_admin_entry_target_control),
):
    del principal
    try:
        return BaseResponse(data=_entry_view(control.resolve(entry_id)))
    except EntryTargetError as error:
        _raise_error(error, _correlation(request))


@router.post("/preview", response_model=BaseResponse[EntryTargetPreviewView])
def preview_entry_target(
    body: EntryTargetCommandInput,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"),
    ],
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"),
    ],
    principal: AdminPrincipal = Depends(require_admin),
    control: AdminEntryTargetControl = Depends(get_admin_entry_target_control),
):
    try:
        preview = control.preview(_command(body, idempotency_key, correlation_id, principal))
        return BaseResponse(data=EntryTargetPreviewView.model_validate(preview, from_attributes=True))
    except EntryTargetError as error:
        _raise_error(error, correlation_id)


@router.post("/apply", response_model=BaseResponse[EntryTargetReceiptView])
def apply_entry_target(
    body: EntryTargetCommandInput,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"),
    ],
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"),
    ],
    principal: AdminPrincipal = Depends(require_admin),
    control: AdminEntryTargetControl = Depends(get_admin_entry_target_control),
):
    request.state.audit_persistence = "admin_entry_target_control_plane"
    try:
        receipt = control.apply(_command(body, idempotency_key, correlation_id, principal))
        request.state.audit_action = "admin.entry_target.apply"
        request.state.audit_resource_type = "admin_entry_target"
        request.state.audit_resource_id = receipt.entry_id
        return BaseResponse(data=_receipt_view(receipt), message="管理端入口 target 已更新")
    except EntryTargetError as error:
        _raise_error(error, correlation_id)


def _command(
    body: EntryTargetCommandInput,
    idempotency_key: str,
    correlation_id: str,
    principal: AdminPrincipal,
) -> SwitchCommand:
    binding = body.required_react_artifact
    artifact = None if binding is None else ArtifactBinding(
        binding.version, binding.digest, binding.api_compatibility_revision
    )
    actor_identity = str(principal.id) if principal.id is not None else principal.username
    return SwitchCommand(
        body.entry_id,
        body.expected_state_revision,
        body.expected_entry_revision,
        body.expected_current_target,
        body.desired_target,
        artifact,
        body.reason_code,
        idempotency_key,
        f"admin:{actor_identity}",
        correlation_id,
    )


def _state_view(state: EntryTargetState) -> EntryTargetStateView:
    return EntryTargetStateView(
        schema_version=state.schema_version,
        registry_revision=state.registry_revision,
        registry_digest=state.registry_digest,
        revision=state.revision,
        entries=[_entry_view(item) for item in state.entries],
        receipt_count=len(state.receipts),
        state_digest=state.state_digest,
    )


def _entry_view(item: EntryTargetRecord) -> EntryTargetView:
    artifact = item.required_react_artifact
    return EntryTargetView(
        entry_id=item.entry_id,
        replacement_group=item.replacement_group,
        current_target=item.current_target,
        streamlit_target=item.streamlit_target,
        react_target=item.react_target,
        required_react_artifact=None if artifact is None else ArtifactBindingView(
            version=artifact.version,
            digest=artifact.digest,
            api_compatibility_revision=artifact.api_compatibility_revision,
        ),
        entry_revision=item.entry_revision,
    )


def _receipt_view(item: SwitchReceipt) -> EntryTargetReceiptView:
    return EntryTargetReceiptView.model_validate(item, from_attributes=True)


def _correlation(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) else "entry-target-correlation-unavailable"


def _raise_error(error: EntryTargetError, correlation_id: str):
    status = {"validation": 422, "not_found": 404, "conflict": 409, "unavailable": 503}.get(
        error.category, 500
    )
    raise HTTPException(
        status_code=status,
        detail={
            "error": {
                "category": error.category,
                "code": error.code,
                "message": error.message,
                "correlation_id": correlation_id,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": error.category == "unavailable",
                "current_version": error.current_revision,
            }
        },
    )
