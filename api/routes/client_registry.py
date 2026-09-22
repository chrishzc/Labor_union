"""Case-centered client registry query and owner-routed mutations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_registry_reader,
    require_registry_writer,
)
from api.dependencies.client_profile import get_client_profile_application
from api.dependencies.client_registry import (
    get_beclass_correction_workflow,
    get_client_registry_order_accounting_export_application,
    get_client_registry_query_application,
)
from api.dependencies.order_terms import get_order_terms_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.client_registry import (
    BeClassCorrectionApplyRequest,
    BeClassCorrectionPreviewRequest,
    ClientRegistryChangeHistoryItemView,
    ClientProfileAdminApplyRequest,
    ClientProfileAdminPreviewRequest,
    ClientRegistryDetailView,
    ClientRegistryPageView,
    RegistryMutationPreviewView,
    RegistryMutationReceiptView,
)
from api.schemas.order_terms import OrderTermsQueryView
from domains.case_import.beclass_correction import BeClassCorrectionError
from domains.case_import.beclass_correction import VALID_MULTI_BIRTH_COUNTS
from domains.case_import.client_import_validation import VALID_CITIES
from domains.clients.profile import (
    ClientProfileValidationError,
    VALID_DELIVERY_TYPES,
    VALID_GENDERS,
    VALID_RESIDENCE_TYPES,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.case_import.beclass_correction_workflow import (
    BeClassCorrectionBlocked,
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
from subsystems.client_profile.order_accounting_export import (
    ClientRegistryOrderAccountingExportApplication,
    OrderAccountingExportQuery,
    XLSX_MEDIA_TYPE,
)


router = APIRouter(prefix="/api/v1/admin/registries/clients", tags=["Client Registry"])

_FIELD_OPTIONS = {
    "client_profile": {
        "gender": ("女", "男"),
        "city": tuple(VALID_CITIES),
        "residence_type": ("電梯大樓", "公寓", "透天", "其他"),
        "delivery_type": ("自然產", "剖腹產", "未定"),
    },
    "client_beclass": {
        "multi_birth_count": ("單胞胎", "雙胞胎"),
    },
}
assert set(_FIELD_OPTIONS["client_profile"]["gender"]) == VALID_GENDERS
assert set(_FIELD_OPTIONS["client_profile"]["residence_type"]) == VALID_RESIDENCE_TYPES
assert set(_FIELD_OPTIONS["client_profile"]["delivery_type"]) == VALID_DELIVERY_TYPES
assert set(_FIELD_OPTIONS["client_beclass"]["multi_birth_count"]) == VALID_MULTI_BIRTH_COUNTS


@router.get("", response_model=BaseResponse[ClientRegistryPageView])
def list_client_registry(
    query: str | None = Query(default=None, max_length=100),
    multi_birth_count: Literal["單胞胎", "雙胞胎"] | None = Query(default=None),
    order_status: str | None = Query(default=None, min_length=1, max_length=50),
    requires_cooking: bool | None = Query(default=None),
    sort_by: Literal["case_no", "customer_name", "service_days", "expected_start_date"] | None = Query(default=None),
    sort_order: Literal["asc", "desc"] | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    after: str | None = Query(default=None, min_length=1, max_length=50),
    offset: int = Query(default=0, ge=0),
    principal: AdminPrincipal = Depends(require_registry_reader),
    application: ClientRegistryQueryApplication = Depends(get_client_registry_query_application),
):
    del principal
    try:
        result = application.list(
            query=query,
            multi_birth_count=multi_birth_count,
            order_status=order_status,
            requires_cooking=requires_cooking,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            after=after,
            offset=offset,
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


@router.get(
    "/export/order-accounting",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
def export_client_registry_order_accounting(
    query: str | None = Query(default=None, max_length=100),
    multi_birth_count: Literal["單胞胎", "雙胞胎"] | None = Query(default=None),
    order_status: str | None = Query(default=None, min_length=1, max_length=50),
    requires_cooking: bool | None = Query(default=None),
    sort_by: Literal["case_no", "customer_name", "service_days", "expected_start_date"] | None = Query(default=None),
    sort_order: Literal["asc", "desc"] | None = Query(default=None),
    principal: AdminPrincipal = Depends(require_registry_reader),
    application: ClientRegistryOrderAccountingExportApplication = Depends(
        get_client_registry_order_accounting_export_application
    ),
):
    del principal
    correlation = uuid4().hex
    try:
        content = application.export(OrderAccountingExportQuery(
            query=query,
            multi_birth_count=multi_birth_count,
            order_status=order_status,
            requires_cooking=requires_cooking,
            sort_by=sort_by,
            sort_order=sort_order,
        ))
        return Response(
            content=content,
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": 'attachment; filename="client-order-accounting.xlsx"'},
        )
    except ValueError as error:
        raise _registry_error(error, correlation) from error
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "client_registry_order_accounting_export_internal_error",
            "訂單帳務匯出失敗。",
            correlation,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "client_registry_order_accounting_export_internal_error",
            "訂單帳務匯出失敗。",
            correlation,
        ) from error


@router.get(
    "/{case_no}/change-history",
    response_model=BaseResponse[tuple[ClientRegistryChangeHistoryItemView, ...]],
)
def get_client_registry_change_history(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_registry_reader),
    application: ClientRegistryQueryApplication = Depends(get_client_registry_query_application),
):
    del principal
    correlation = uuid4().hex
    try:
        history = application.history(case_no)
        return BaseResponse(
            data=tuple(
                ClientRegistryChangeHistoryItemView.model_validate(item, from_attributes=True)
                for item in history
            ),
            message="成功取得案件變更歷程",
        )
    except (ValueError, ClientRegistryContractError) as error:
        raise _registry_error(error, correlation) from error
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "client_registry_history_internal_error",
            "案件變更歷程查詢失敗。",
            correlation,
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
                "source_kind": detail.beclass.source_kind,
                "version": detail.beclass.version,
                "values": detail.beclass.values,
                "field_capabilities": _beclass_field_capabilities(detail),
            },
            "order_information": {
                "status": detail.order_information.status,
                "values": detail.order_information.values,
                "field_issues": detail.order_information.field_issues,
            },
            "finance": {
                "status": detail.finance.status,
                "code": detail.finance.code,
                "values": detail.finance.values,
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
        str(field): {
            "owner": owner,
            "editable": editable,
            "reason": reason,
            "options": _FIELD_OPTIONS.get(owner, {}).get(str(field)),
        }
        for field in values
    }


def _beclass_field_capabilities(detail) -> dict[str, dict[str, Any]]:
    ready = detail.beclass.status == "ready"
    capabilities = _field_capabilities(
        detail.beclass.values or {},
        "client_beclass",
        ready,
        None if ready else f"beclass_{detail.beclass.status}",
    )
    if detail.beclass.financial_fields_locked and "multi_birth_count" in capabilities:
        capabilities["multi_birth_count"] = {
            **capabilities["multi_birth_count"],
            "editable": False,
            "reason": "multi_birth_count_locked_after_service_start",
        }
    return capabilities


def _registry_error(error: Exception, correlation: str) -> HTTPException:
    return typed_http_error(422, "validation", str(error) or "client_registry_invalid", "客戶名冊資料未通過驗證。", correlation)


def _raise_owner_error(error: Exception, correlation: str, message: str) -> None:
    code = str(error) or "registry_mutation_failed"
    if isinstance(error, (ClientProfileNotFoundError, BeClassCorrectionNotFound)):
        status, category = 404, "not_found"
    elif isinstance(error, (ClientProfileStaleError, ClientProfileRequestConflictError, BeClassCorrectionConflict, BeClassCorrectionBlocked)) or "stale" in code or "idempotency" in code or "collision" in code:
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
