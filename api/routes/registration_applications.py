"""
File: registration_applications.py
Description: 非市民需求申請之內部審核與手動新增歷史非市民案件 API。
"""
from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_admin, admin_actor_context
from api.dependencies.registration_applications import get_registration_review_application
from api.schemas.base import BaseResponse
from api.error_contracts import typed_http_error
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflictError, ProvisionalRegistrationStorageError,
)
from subsystems.line.identity_application import LineIdentityConflictError
from subsystems.case_import.registration_staging import RegistrationReviewApplication
from domains.case_import.refund_account import mask_refund_values, REFUND_SURVEY_FIELDS
from shared_kernel.identities import CorrelationId
from subsystems.case_import.case_import_workflow import CaseImportWorkflowError


router = APIRouter(prefix="/api/v1/admin/registration-applications", tags=["非市民申請審核"])


class ApplicationField(BaseModel):
    label: str
    value: str


class ApplicationView(BaseModel):
    registration_id: int
    version: int
    name: str | None
    phone: str | None
    status: str
    submitted_at_utc: str
    expires_at_utc: str
    approved: bool
    fields: list[ApplicationField]
    registration_kind: str = "subsidy"
    case_no: str | None = None
    approved_at_utc: str | None = None


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class VirtualAccountCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    virtual_account: str = Field(min_length=1, max_length=50)
    case_no: str | None = None


class VirtualAccountCheckView(BaseModel):
    virtual_account: str
    conflict: bool
    conflict_case_no: str | None = None
    conflict_case_status: str | None = None
    conflict_case_client_name: str | None = None
    conflict_case_client_phone: str | None = None
    has_accounting_details: bool = False
    received_total_ntd: int = 0
    accounting_description: str = ""
    cancel_reason: str | None = None


class ManualNonCitizenCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    case_no: str = Field(min_length=1, max_length=50)
    virtual_account: str = Field(min_length=14, max_length=14)
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=20)
    gender: str = "女"
    identity_status: str = "非市民"
    service_start_date: str = Field(description="YYYY-MM-DD")
    service_end_date: str | None = None
    service_days: int = Field(ge=1)
    service_time: str
    service_type: str = "連續服務"
    delivery_type: str = "自然產"
    residence_type: str = "電梯大樓"
    baby_info: str = "單胞胎"
    city: str | None = None
    address: str | None = None
    due_month: str | None = None
    birth_date: str | None = None
    email: str | None = None
    line_id: str | None = None
    notes: str | None = None
    admin_notes: str | None = None
    requires_cooking: bool = False
    refund_bank_code: str | None = None
    refund_account_no: str | None = None
    override_conflict: bool = False
    override_case_no: str | None = None


class ManualNonCitizenCaseReceiptView(BaseModel):
    case_no: str
    virtual_account: str
    client_id: int
    overridden_case_no: str | None = None
    message: str


def _view(snapshot) -> ApplicationView:
    candidate = snapshot.candidate
    common = dict(registration_id=snapshot.registration_id, version=snapshot.version,
        status=snapshot.status, submitted_at_utc=snapshot.submitted_at_utc.isoformat(),
        expires_at_utc=snapshot.expires_at_utc.isoformat(),
        registration_kind=snapshot.registration_kind, case_no=snapshot.case_no,
        approved=snapshot.status == 'approved',
        approved_at_utc=snapshot.approved_at_utc.isoformat() if snapshot.approved_at_utc else None)
    if candidate is None:
        return ApplicationView(**common, name=None, phone=None, fields=[])
    labels = {"name": "姓名", "phone": "電話", "address": "服務地址", "city": "縣市",
              "service_days": "需求天數", "due_month": "預計日期", "gender": "性別",
              "email": "電子郵件", "birth_date": "生日", "tel": "市話", "ext": "分機", "zip_code": "郵遞區號"}
    values = {**candidate.client_payload, **{key: value for key, value in candidate.beclass_payload.items() if key != "survey_details"}}
    values.pop("line_user_id", None)
    values.update({key: value for key, value in candidate.beclass_payload["survey_details"].items() if not key.startswith("_")})
    # Review is authorized to see the questionnaire, but routine views still mask bank accounts.
    values = mask_refund_values(values)
    if REFUND_SURVEY_FIELDS[1] in values:
        values[REFUND_SURVEY_FIELDS[1]] = mask_refund_values({"refund_account_no": values[REFUND_SURVEY_FIELDS[1]]})["refund_account_no"]
    fields = [ApplicationField(label=labels.get(key, key), value=("未填寫" if value is None else
              json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)))
              for key, value in values.items()]
    return ApplicationView(**common, name=str(candidate.client_payload["name"]),
                           phone=str(candidate.client_payload["phone"]), fields=fields)



def _translate(operation):
    try:
        return operation()
    except (ProvisionalRegistrationConflictError, LineIdentityConflictError):
        raise typed_http_error(409, "conflict", "registration_application_conflict",
            "申請或 LINE 綁定狀態已變更，請重新查詢後確認。", uuid4().hex) from None
    except ProvisionalRegistrationStorageError:
        raise typed_http_error(503, "unavailable", "registration_application_unavailable",
            "申請資料暫時無法使用，請稍後重試。", uuid4().hex, retryable=True) from None
    except CaseImportWorkflowError as error:
        category = error.error.category.value
        status = {"validation": 422, "domain_blocked": 422, "conflict": 409,
                  "idempotency_mismatch": 409, "forbidden": 403, "not_found": 404,
                  "unavailable": 503, "internal": 500}[category]
        raise typed_http_error(status, category, error.error.code,
            "正式案件建立未完成，請依提示檢查資料後重新查詢。", error.error.correlation_id.value,
            retryable=error.error.retryable) from None


@router.get("", response_model=BaseResponse[list[ApplicationView]])
def pending_applications(after_id: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200),
                         principal=Depends(require_admin),
                         application: RegistrationReviewApplication = Depends(get_registration_review_application)):
    return BaseResponse(data=_translate(lambda: [_view(item) for item in application.pending_registrations(after_id=after_id, limit=limit)]))


@router.get("/{registration_id}", response_model=BaseResponse[ApplicationView])
def application_detail(registration_id: int, principal=Depends(require_admin),
                        application: RegistrationReviewApplication = Depends(get_registration_review_application)):
    return BaseResponse(data=_translate(lambda: _view(application.registration_application(registration_id))))


@router.post("/{registration_id}/approve", response_model=BaseResponse[ApplicationView])
def approve_application(registration_id: int, body: ApprovalRequest, principal=Depends(require_admin),
                         application: RegistrationReviewApplication = Depends(get_registration_review_application)):
    def approve():
        snapshot = application.approve_registration(registration_id, body.expected_version,
            admin_actor_context(principal).actor_id, CorrelationId(f"registration-approval:{registration_id}"))
        if snapshot.status == "approved":
            from api.dependencies.line_runtime import publish_line_wakeup_best_effort
            publish_line_wakeup_best_effort()
        return _view(snapshot)
    return BaseResponse(data=_translate(approve), message="需求申請已核准，正式客戶資料已建立。")


@router.post("/{registration_id}/reject", response_model=BaseResponse[ApplicationView])
def reject_application(registration_id: int, body: ApprovalRequest, principal=Depends(require_admin),
                       application: RegistrationReviewApplication = Depends(get_registration_review_application)):
    snapshot = _translate(lambda: application.reject_registration(
        registration_id, body.expected_version, admin_actor_context(principal).actor_id))
    return BaseResponse(data=_view(snapshot), message=("申請已到期，問卷內容已清除。"
        if snapshot.status == "expired" else "非市民申請已拒絕，問卷內容已清除。"))


@router.post("/manual-non-citizen/check", response_model=BaseResponse[VirtualAccountCheckView])
def check_manual_non_citizen_account(
    body: VirtualAccountCheckRequest,
    principal=Depends(require_admin),
):
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.case_import.non_citizen_registration_application import (
        check_case_number_duplicate,
        check_virtual_account_conflict,
    )
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            if body.case_no and check_case_number_duplicate(cursor, body.case_no.strip()):
                raise typed_http_error(
                    422, "validation", "case_no_duplicate",
                    f"案件編號「{body.case_no.strip()}」已存在，不能與其他案件重複。", uuid4().hex
                )
            result = check_virtual_account_conflict(cursor, body.virtual_account.strip(), body.case_no.strip() if body.case_no else None)
            return BaseResponse(data=VirtualAccountCheckView(**result))
    except ValueError as exc:
        raise typed_http_error(422, "validation", "invalid_input", str(exc), uuid4().hex) from exc
    finally:
        connection.close()


@router.post("/manual-non-citizen", response_model=BaseResponse[ManualNonCitizenCaseReceiptView])
def create_manual_non_citizen(
    body: ManualNonCitizenCaseCreateRequest,
    principal=Depends(require_admin),
):
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.case_import.non_citizen_registration_application import create_manual_non_citizen_case
    actor = admin_actor_context(principal).actor_id
    connection = get_connection()
    try:
        result = create_manual_non_citizen_case(connection, body.model_dump(), actor)
        return BaseResponse(
            data=ManualNonCitizenCaseReceiptView(**result),
            message=result["message"],
        )
    except ValueError as exc:
        raise typed_http_error(422, "validation", "manual_non_citizen_invalid", str(exc), uuid4().hex) from exc
    except CaseImportWorkflowError as exc:
        raise typed_http_error(
            422, "domain_blocked", exc.error.code, f"建案失敗：{exc.error.message}",
            exc.error.correlation_id.value
        ) from exc
    finally:
        connection.close()
