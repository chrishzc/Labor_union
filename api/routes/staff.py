"""
File: staff.py
Description: 提供管理員會話保護的 bounded Staff 摘要 cursor 查詢與退役全量入口。
"""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_case_preference_summary import (
    get_staff_case_preference_mutation_workflow,
    get_staff_case_preference_summary_application,
)
from api.dependencies.staff_summary import get_staff_summary_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_case_preference_summary import (
    StaffCasePreferenceApplyReceiptView,
    StaffCasePreferenceApplyRequest,
    StaffCasePreferencePreviewView,
    StaffCasePreferenceSnapshotView,
    StaffCasePreferenceSummaryView,
)
from api.schemas.staff_summary import StaffSummaryPageView, StaffSummaryView
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.case_preference_summary_mutation import StaffCasePreferenceMutationWorkflow
from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceSummaryContractError,
    StaffCasePreferenceSummaryQueryApplication,
)
from subsystems.staff.summary_query import (
    StaffSummaryContractError,
    StaffSummaryQueryApplication,
    StaffSummaryQueryRequest,
)

router = APIRouter(prefix="/api/v1/staff", tags=["Staff 服務人員/月嫂名冊"])


@router.get("/summaries", response_model=BaseResponse[StaffSummaryPageView])
def get_staff_summaries(
    page_size: int = Query(default=200, ge=1, le=200),
    after_id: int | None = Query(default=None, ge=1),
    staff_id: int | None = Query(default=None, ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffSummaryQueryApplication = Depends(get_staff_summary_application),
) -> BaseResponse[StaffSummaryPageView]:
    """Return a bounded staff selector page without exposing the staff master."""
    del principal
    correlation = correlation_id or uuid4().hex
    if staff_id is not None and after_id is not None:
        raise typed_http_error(
            422,
            "validation",
            "staff_summary_query_params_conflict",
            "staff_id 與 after_id 不得同時提供。",
            correlation,
        )
    try:
        page = application.query(
            StaffSummaryQueryRequest(
                page_size=page_size,
                after_id=after_id,
                staff_id=staff_id,
            )
        )
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            correlation,
        ) from error
    except StaffSummaryContractError as error:
        raise internal_query_error(
            "staff_summary_projection_invalid",
            "服務人員摘要投影契約無效。",
            correlation,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            correlation,
        ) from error
    return BaseResponse(
        data=StaffSummaryPageView(
            items=[StaffSummaryView.model_validate(item, from_attributes=True) for item in page.items],
            next_cursor=page.next_cursor,
        ),
        message="成功取得服務人員摘要",
    )


@router.get(
    "/{staff_id}/case-preference-summary",
    response_model=BaseResponse[StaffCasePreferenceSummaryView],
)
def get_staff_case_preference_summary(
    staff_id: int = Path(..., ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffCasePreferenceSummaryQueryApplication = Depends(
        get_staff_case_preference_summary_application
    ),
) -> BaseResponse[StaffCasePreferenceSummaryView]:
    """Return one bounded Staff case-preference projection for roster consumers."""
    del principal
    correlation = correlation_id or uuid4().hex
    try:
        summary = application.get(staff_id)
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_case_preference_summary_query_internal_error",
            "服務人員案件偏好摘要查詢失敗。",
            correlation,
        ) from error
    except StaffCasePreferenceSummaryContractError as error:
        raise internal_query_error(
            "staff_case_preference_summary_projection_invalid",
            "服務人員案件偏好摘要投影契約無效。",
            correlation,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "staff_case_preference_summary_query_internal_error",
            "服務人員案件偏好摘要查詢失敗。",
            correlation,
        ) from error

    if summary is None:
        raise typed_http_error(404, "not_found", "staff_not_found", "查無服務人員。", correlation)

    return BaseResponse(
        data=StaffCasePreferenceSummaryView.from_summary(summary),
        message="成功取得服務人員案件偏好摘要",
    )


@router.post(
    "/{staff_id}/case-preference-summary/preview",
    response_model=BaseResponse[StaffCasePreferencePreviewView],
)
def preview_staff_case_preference_summary(
    body: StaffCasePreferenceSnapshotView,
    staff_id: int = Path(..., ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    workflow: StaffCasePreferenceMutationWorkflow = Depends(get_staff_case_preference_mutation_workflow),
) -> BaseResponse[StaffCasePreferencePreviewView]:
    del principal
    correlation = correlation_id or uuid4().hex
    try:
        preview = workflow.preview(staff_id, body.to_domain())
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_case_preference_preview_internal_error",
            "服務人員案件偏好預覽失敗。",
            correlation,
        ) from error
    except (ValueError, StaffCasePreferenceSummaryContractError) as error:
        _raise_case_preference_mutation_error(error, correlation)
    return BaseResponse(
        data=StaffCasePreferencePreviewView(
            staff_id=preview.staff_id,
            before=StaffCasePreferenceSnapshotView.from_domain(preview.before),
            after=StaffCasePreferenceSnapshotView.from_domain(preview.after),
            preview_fingerprint=preview.fingerprint.value,
        ),
        message="成功預覽服務人員案件偏好變更",
    )


@router.post(
    "/{staff_id}/case-preference-summary/apply",
    response_model=BaseResponse[StaffCasePreferenceApplyReceiptView],
)
def apply_staff_case_preference_summary(
    body: StaffCasePreferenceApplyRequest,
    staff_id: int = Path(..., ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    workflow: StaffCasePreferenceMutationWorkflow = Depends(get_staff_case_preference_mutation_workflow),
) -> BaseResponse[StaffCasePreferenceApplyReceiptView]:
    del principal
    correlation = correlation_id or uuid4().hex
    try:
        receipt = workflow.apply(
            staff_id,
            body.snapshot.to_domain(),
            PreviewFingerprint(body.preview_fingerprint),
        )
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_case_preference_apply_internal_error",
            "服務人員案件偏好儲存失敗。",
            correlation,
        ) from error
    except (ValueError, StaffCasePreferenceSummaryContractError) as error:
        _raise_case_preference_mutation_error(error, correlation)
    return BaseResponse(
        data=StaffCasePreferenceApplyReceiptView(
            staff_id=receipt.staff_id,
            preview_fingerprint=receipt.preview_fingerprint.value,
            snapshot=StaffCasePreferenceSnapshotView.from_domain(receipt.snapshot),
        ),
        message="服務人員案件偏好已更新",
    )


def _raise_case_preference_mutation_error(error: Exception, correlation: str) -> None:
    code = str(error) or "staff_case_preference_validation_error"
    if code == "staff_not_found":
        raise typed_http_error(404, "not_found", code, "查無服務人員。", correlation) from error
    if code == "stale_preview":
        raise typed_http_error(409, "conflict", code, "案件偏好資料已變更，請重新預覽。", correlation) from error
    if isinstance(error, StaffCasePreferenceSummaryContractError):
        raise internal_query_error(
            "staff_case_preference_summary_projection_invalid",
            "服務人員案件偏好摘要投影契約無效。",
            correlation,
        ) from error
    raise typed_http_error(422, "validation", code, "案件偏好資料不符合可儲存契約。", correlation) from error


@router.get("", include_in_schema=False)
def get_all_staff() -> None:
    """Reject the retired unbounded staff directory endpoint."""
    raise HTTPException(
        status_code=410,
        detail="全量服務人員名冊已退役，請使用 /summaries cursor 分頁查詢。",
    )
