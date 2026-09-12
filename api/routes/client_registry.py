"""Case-centered client registry query and owner-routed mutations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_registry_reader,
    require_registry_writer,
)
from api.dependencies.client_profile import get_client_profile_application
from api.dependencies.client_registry import (
    get_beclass_correction_workflow,
    get_client_registry_query_application,
)
from api.dependencies.order_terms import get_order_terms_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.client_registry import (
    BeClassCorrectionApplyRequest,
    BeClassCorrectionPreviewRequest,
    ClientProfileAdminApplyRequest,
    ClientProfileAdminPreviewRequest,
    ClientRegistryDetailView,
    ClientRegistryPageView,
    RegistryMutationPreviewView,
    RegistryMutationReceiptView,
)
from api.schemas.order_terms import OrderTermsQueryView
from domains.case_import.beclass_correction import BeClassCorrectionError
from domains.clients.profile import ClientProfileValidationError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.case_import.beclass_correction_workflow import (
    BeClassCorrectionConflict,
    BeClassCorrectionNotFound,
    BeClassCorrectionWorkflow,
)
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.contracts import (
    ClientProfileNotFoundError,
    ClientProfileRequestConflictError,
    ClientProfileStaleError,
)
from subsystems.client_profile.registry_query import (
    ClientRegistryContractError,
    ClientRegistryNotFound,
    ClientRegistryQueryApplication,
)


router = APIRouter(prefix="/api/v1/admin/registries/clients", tags=["Client Registry"])


@router.get("", response_model=BaseResponse[ClientRegistryPageView])
def list_client_registry(
    query: str | None = Query(default=None, max_length=100),
    has_baby_info: bool | None = Query(default=None),
    service_days: int | None = Query(default=None, gt=0),
    requires_cooking: bool | None = Query(default=None),
    sort_by: Literal["case_no", "customer_name", "service_days", "expected_start_date"] | None = Query(default=None),
    sort_order: Literal["asc", "desc"] | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    after: str | None = Query(default=None, min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_registry_reader),
    application: ClientRegistryQueryApplication = Depends(get_client_registry_query_application),
):
    del principal
    try:
        result = application.list(
            query=query,
            has_baby_info=has_baby_info,
            service_days=service_days,
            requires_cooking=requires_cooking,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            after=after,
        )
        return BaseResponse(
            data=ClientRegistryPageView.model_validate(result, from_attributes=True),
            message="成功取得客戶名冊",
        )
    except (ValueError, ClientRegistryContractError) as error:
        raise _registry_error(error, uuid4().hex) from error
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "client_registry_query_internal_error",
            "客戶名冊查詢失敗。",
            uuid4().hex,
        ) from error


@router.get("/{case_no}", response_model=BaseResponse[ClientRegistryDetailView])
def get_client_registry(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_registry_reader),
    application: ClientRegistryQueryApplication = Depends(get_client_registry_query_application),
    order_terms=Depends(get_order_terms_application),
):
    del principal
    correlation = uuid4().hex
    try:
        detail = application.query(case_no)
        payload = {
            "case_no": detail.case_no,
            "client": {
                "client_id": detail.client.client_id,
                "version": detail.client.version,
                "values": detail.client.values,
                "field_capabilities": _field_capabilities(detail.client.values, "client_profile", True),
            },
            "beclass": {
                "status": detail.beclass.status,
                "record_id": detail.beclass.record_id,
                "version": detail.beclass.version,
                "values": detail.beclass.values,
                "field_capabilities": _field_capabilities(
                    detail.beclass.values or {},
                    "client_beclass",
                    detail.beclass.status == "ready",
                    None if detail.beclass.status == "ready" else f"beclass_{detail.beclass.status}",
                ),
            },
            "order_terms": _order_terms_section(order_terms, case_no),
        }
        return BaseResponse(
            data=ClientRegistryDetailView.model_validate(payload, from_attributes=True),
            message="成功取得案件客戶名冊",
        )
    except ClientRegistryNotFound as error:
        raise typed_http_error(404, "not_found", "client_registry_not_found", "查無案件客戶資料。", correlation) from error
    except (ValueError, ClientRegistryContractError) as error:
        raise _registry_error(error, correlation) from error
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error("client_registry_query_internal_error", "客戶名冊查詢失敗。", correlation) from error


@router.post("/{case_no}/profile/preview", response_model=BaseResponse[RegistryMutationPreviewView])
def preview_client_profile(
    body: ClientProfileAdminPreviewRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_registry_writer),
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    del principal
    correlation = uuid4().hex
    try:
        preview = application.preview_admin(
            case_no,
            body.changes.model_dump(exclude_unset=True),
            ExpectedVersion(body.expected_version),
        )
        return BaseResponse(data=RegistryMutationPreviewView(
            owner="client_profile",
            aggregate_identity=case_no,
            current_version=preview.current_version,
            before=dict(preview.before),
            after=dict(preview.requested),
            preview_fingerprint=preview.preview_fingerprint.value,
        ), message="成功產生客戶主檔變更預覽")
    except Exception as error:
        _raise_owner_error(error, correlation, "客戶主檔變更無法預覽。")


@router.post("/{case_no}/profile/apply", response_model=BaseResponse[RegistryMutationReceiptView])
def apply_client_profile(
    body: ClientProfileAdminApplyRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_registry_writer),
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    try:
        receipt = application.apply_admin(
            case_no,
            body.changes.model_dump(exclude_unset=True),
            ExpectedVersion(body.expected_version),
            admin_actor_context(principal),
            body.reason,
            PreviewFingerprint(body.preview_fingerprint),
            IdempotencyKey(idempotency_key),
            CorrelationId(correlation_id),
        )
        return BaseResponse(data=RegistryMutationReceiptView(
            owner="client_profile",
            aggregate_identity=receipt.case_no,
            resulting_version=receipt.resulting_version,
            changed_fields=receipt.changed_fields,
            preview_fingerprint=receipt.preview_fingerprint.value,
            idempotency_key=receipt.idempotency_key,
            replayed=receipt.replayed,
            readback=dict(receipt.readback.values),
        ), message="客戶主檔已更新")
    except Exception as error:
        _raise_owner_error(error, correlation_id, "客戶主檔更新失敗。")


@router.post("/{case_no}/beclass/preview", response_model=BaseResponse[RegistryMutationPreviewView])
def preview_beclass_correction(
    body: BeClassCorrectionPreviewRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: BeClassCorrectionWorkflow = Depends(get_beclass_correction_workflow),
):
    del principal
    correlation = uuid4().hex
    try:
        preview = workflow.preview(
            case_no,
            body.changes.model_dump(exclude_unset=True),
            ExpectedVersion(body.expected_version),
        )
        return BaseResponse(data=RegistryMutationPreviewView(
            owner="client_beclass",
            aggregate_identity=case_no,
            current_version=preview.current_version,
            before=dict(preview.before),
            after=dict(preview.after),
            preview_fingerprint=preview.preview_fingerprint.value,
        ), message="成功產生 BeClass 修正預覽")
    except Exception as error:
        _raise_owner_error(error, correlation, "BeClass 修正無法預覽。")


@router.post("/{case_no}/beclass/apply", response_model=BaseResponse[RegistryMutationReceiptView])
def apply_beclass_correction(
    body: BeClassCorrectionApplyRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: BeClassCorrectionWorkflow = Depends(get_beclass_correction_workflow),
):
    try:
        receipt = workflow.apply(
            case_no,
            body.changes.model_dump(exclude_unset=True),
            ExpectedVersion(body.expected_version),
            PreviewFingerprint(body.preview_fingerprint),
            IdempotencyKey(idempotency_key),
            admin_actor_context(principal),
            body.reason,
            CorrelationId(correlation_id),
        )
        return BaseResponse(data=RegistryMutationReceiptView(
            owner="client_beclass",
            aggregate_identity=receipt.case_no,
            resulting_version=receipt.resulting_version,
            changed_fields=receipt.changed_fields,
            preview_fingerprint=receipt.preview_fingerprint.value,
            idempotency_key=receipt.idempotency_key.value,
            replayed=receipt.replayed,
            readback=dict(receipt.readback.effective),
        ), message="BeClass 有效資料已修正")
    except Exception as error:
        _raise_owner_error(error, correlation_id, "BeClass 修正失敗。")


def _order_terms_section(application, case_no: str) -> dict[str, Any]:
    try:
        facts = application.query(case_no)
    except ValueError as error:
        code = str(error)
        return {
            "status": "not_found" if code == "order_not_found" else "not_ready",
            "code": code,
            "data": None,
            "field_capabilities": {},
        }
    return {
        "status": "ready",
        "code": None,
        "data": OrderTermsQueryView.model_validate({
            "case_no": facts.order.case_no,
            "order_version": facts.order.version,
            "scheduling_version": facts.scheduling.aggregate_version,
            "scheduling_generation": facts.scheduling.generation_number,
            "client_finance_version": facts.client_finance.account_version,
            "payroll_version": facts.payroll.payroll_version,
            "service_data_locked": facts.order.service_data_locked,
            "terms": facts.order.terms.canonical_payload(),
        }),
        "field_capabilities": _field_capabilities(
            facts.order.terms.canonical_payload(), "order_terms", not facts.order.service_data_locked,
            "order_terms_locked" if facts.order.service_data_locked else None,
        ),
    }


def _field_capabilities(
    values: Mapping[str, Any],
    owner: str,
    editable: bool,
    reason: str | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        str(field): {"owner": owner, "editable": editable, "reason": reason}
        for field in values
    }


def _registry_error(error: Exception, correlation: str) -> HTTPException:
    return typed_http_error(422, "validation", str(error) or "client_registry_invalid", "客戶名冊資料未通過驗證。", correlation)


def _raise_owner_error(error: Exception, correlation: str, message: str) -> None:
    code = str(error) or "registry_mutation_failed"
    if isinstance(error, (ClientProfileNotFoundError, BeClassCorrectionNotFound)):
        status, category = 404, "not_found"
    elif isinstance(error, (ClientProfileStaleError, ClientProfileRequestConflictError, BeClassCorrectionConflict)) or "stale" in code or "idempotency" in code or "collision" in code:
        status = 409
        category = "idempotency_mismatch" if "idempotency" in code else "conflict"
    elif isinstance(error, (ClientProfileValidationError, BeClassCorrectionError, ValueError)):
        status, category = 422, "validation"
    elif isinstance(error, HTTPException):
        raise error
    else:
        raise internal_query_error("registry_mutation_internal_error", message, correlation) from error
    raise typed_http_error(status, category, code, message, correlation) from error


__all__ = ["router"]
