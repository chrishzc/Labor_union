"""Authenticated manual qualification Query/Preview/Apply."""
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import require_admin, admin_actor_context
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_qualification_editing import QualificationFactsBody, QualificationApplyBody, QualificationSnapshotView, QualificationReceiptView
from domains.staff.qualification_editing import QualificationEditingError
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.staff_qualification_editing_repository import MySqlStaffQualificationEditingRepository
from subsystems.staff.qualification_editing_workflow import StaffQualificationEditingWorkflow

router = APIRouter(prefix="/api/v1/staff", tags=["Staff Qualification Editing"])


def get_qualification_editing_workflow():
    connection = get_connection()
    try:
        yield StaffQualificationEditingWorkflow(MySqlStaffQualificationEditingRepository(connection), lambda: MySqlUnitOfWork(connection))
    finally:
        connection.close()


def _raise(error, correlation=None):
    code = str(error)
    if isinstance(error, (IntegrityError, OperationalError)):
        code = "staff_qualification_concurrent_conflict" if error.args[0] in (1062, 1205, 1213) else "staff_qualification_storage_unavailable"
    if code.endswith("not_found"):
        status, category, message = 404, "not_found", "找不到指定月嫂。"
    elif code.endswith(("stale_snapshot", "stale_preview", "idempotency_conflict", "concurrent_conflict")):
        status, category, message = 409, "conflict", "資料已變更或項目衝突，請重新查詢後再預覽。"
    elif code.endswith("storage_unavailable"):
        status, category, message = 503, "unavailable", "資格資料暫時無法儲存。"
    else:
        status, category, message = 422, "validation", "請確認資格欄位內容、重複項目及異動原因。"
    raise typed_http_error(status, category, code, message, correlation or uuid4().hex)


@router.get("/{staff_id}/qualification-editing", response_model=BaseResponse[QualificationSnapshotView])
def query(staff_id: int = Path(gt=0), principal=Depends(require_admin), workflow=Depends(get_qualification_editing_workflow)):
    try:
        return BaseResponse(data=workflow.query(staff_id), message="成功取得可編輯資格")
    except (QualificationEditingError, IntegrityError, OperationalError) as error:
        _raise(error)


@router.post("/{staff_id}/qualification-editing/preview", response_model=BaseResponse[QualificationSnapshotView])
def preview(body: QualificationFactsBody, staff_id: int = Path(gt=0), principal=Depends(require_admin), workflow=Depends(get_qualification_editing_workflow)):
    try:
        return BaseResponse(data=workflow.preview(staff_id, body.facts()), message="資格預覽完成，尚未儲存")
    except (QualificationEditingError, IntegrityError, OperationalError) as error:
        _raise(error)


@router.post("/{staff_id}/qualification-editing/apply", response_model=BaseResponse[QualificationReceiptView])
def apply(body: QualificationApplyBody, staff_id: int = Path(gt=0),
          idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
          correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
          principal=Depends(require_admin), workflow=Depends(get_qualification_editing_workflow)):
    try:
        result = workflow.apply(staff_id, body.facts(), expected_snapshot=body.expected_snapshot_fingerprint,
                                preview=body.preview_fingerprint, key=idempotency_key,
                                actor=admin_actor_context(principal).actor_id, reason=body.reason, correlation=correlation_id)
        return BaseResponse(data=result, message="資格資料已儲存")
    except (QualificationEditingError, IntegrityError, OperationalError) as error:
        _raise(error, correlation_id)
