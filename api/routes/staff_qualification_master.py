"""
File: staff_qualification_master.py
Description: 提供選定 Staff qualification master 的 authenticated、唯讀、typed GET。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_admin
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.staff_qualification_master import StaffQualificationMasterView
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_qualification_master_repository import (
    MySqlStaffQualificationMasterRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.qualification_master_query import (
    QualificationMasterQueryApplication,
    QualificationMasterContractError,
    StaffQualificationMaster,
    StaffQualificationMasterQuery,
    StaffQualificationMasterQueryService,
    StaffQualificationNotFound,
)


router = APIRouter(prefix="/api/v1/staff", tags=["Staff Qualification Master"])


def get_staff_qualification_master_application() -> Iterator[QualificationMasterQueryApplication]:
    """建立單次 query connection；repository 不擁有 commit。"""
    connection = get_connection()
    try:
        yield QualificationMasterQueryApplication(
            StaffQualificationMasterQueryService(
                MySqlStaffQualificationMasterRepository(connection)
            )
        )
    finally:
        connection.close()


@router.get(
    "/{staff_id}/qualification-master",
    response_model=BaseResponse[StaffQualificationMasterView],
    responses={
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢月嫂資格主檔"},
        404: {"model": GlobalTypedErrorResponseView, "description": "月嫂不存在"},
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "月嫂資格主檔查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "月嫂資格主檔資料暫時無法使用"},
    },
)
def query_staff_qualification_master(
    staff_id: int = Path(..., gt=0),
    as_of: date | None = Query(default=None),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: QualificationMasterQueryApplication = Depends(
        get_staff_qualification_master_application
    ),
) -> BaseResponse[StaffQualificationMasterView]:
    del principal
    correlation = correlation_id or uuid4().hex
    try:
        result = application.query(
            StaffQualificationMasterQuery(staff_id, as_of or date.today())
        )
        return BaseResponse(
            data=_master_view(result),
            message="成功取得服務人員資格與可服務期間摘要",
        )
    except StaffQualificationNotFound as error:
        raise typed_http_error(
            404,
            "not_found",
            "staff_qualification_staff_not_found",
            "找不到指定服務人員。",
            correlation,
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(
            503,
            "unavailable",
            "staff_qualification_storage_unavailable",
            "服務人員資格資料暫時無法取得。",
            correlation,
            retryable=True,
        ) from error
    except QualificationMasterContractError as error:
        raise typed_http_error(
            500,
            "internal",
            "staff_qualification_projection_invalid",
            "服務人員資格投影契約無效。",
            correlation,
        ) from error
    except (TypeError, ValueError) as error:
        raise typed_http_error(
            500,
            "internal",
            "staff_qualification_projection_invalid",
            "服務人員資格投影資料無效。",
            correlation,
        ) from error
    except Exception as error:
        raise typed_http_error(
            500,
            "internal",
            "staff_qualification_query_internal_error",
            "服務人員資格查詢失敗。",
            correlation,
        ) from error


def _master_view(result: StaffQualificationMaster) -> StaffQualificationMasterView:
    return StaffQualificationMasterView.model_validate(
        {
            "staff_id": result.staff_id,
            "staff_name": result.staff_name,
            "as_of": result.as_of,
            "overall_availability": result.overall_availability,
            "availability_reason": result.availability_reason,
            "sections": [
                {
                    "kind": section.kind,
                    "owner": section.owner,
                    "availability": section.availability,
                    "availability_reason": section.availability_reason,
                    "source_identity": section.source_identity,
                    "source_version": section.source_version,
                    "items": [
                        {
                            "code": item.code,
                            "value": item.value,
                            "detail": item.detail,
                            "source_identity": item.source_identity,
                            "source_version": item.source_version,
                            "valid_from": item.valid_from,
                            "valid_until": item.valid_until,
                            "availability": item.availability,
                            "availability_reason": item.availability_reason,
                        }
                        for item in section.items
                    ],
                }
                for section in result.sections
            ],
        }
    )


__all__ = ["get_staff_qualification_master_application", "router"]
