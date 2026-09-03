"""
File: operations_reports.py
Description: 提供自選期間營運報表 strict JSON Query 與同 candidate 的三分頁 XLSX 匯出。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from api.dependencies.admin_auth import require_admin
from api.dependencies.operations_reports import (
    get_weekly_operations_report_query,
    get_weekly_report_batch_service,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.operations_reports import (
    CloseWeeklyBatchRequest,
    UnclosedCaseView,
    UpdateWeeklyBatchRequest,
    WeeklyBatchView,
    WeeklyOperationsReportView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.reporting.weekly_operations_report_export import export_weekly_operations_report
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery
from subsystems.reporting.weekly_report_batch_service import WeeklyReportBatchService


router = APIRouter(prefix="/api/v1/operations-reports", tags=["Operations Reports"])
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/weekly",
    response_model=BaseResponse[WeeklyOperationsReportView],
)
def query_weekly_operations_report(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    promotion_count: int | None = Query(None, ge=0),
    inquiry_count: int | None = Query(None, ge=0),
    annual_ytd: bool = Query(False),
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        _reject_legacy_week_start(request)
        report = query.query(
            start_date,
            end_date,
            promotion_count=promotion_count,
            inquiry_count=inquiry_count,
            annual_ytd=annual_ytd,
        )
        view = _weekly_report_view(report)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_operations_report_invalid",
            "起日不得晚於迄日。",
            "weekly-operations-report",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_operations_report_internal_error",
            "營運報表查詢失敗。",
            "weekly-operations-report",
        ) from exc
    return BaseResponse(data=view, message="Weekly operations report")


@router.get("/weekly/export")
def export_weekly_operations_report_xlsx(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    promotion_count: int | None = Query(None, ge=0),
    inquiry_count: int | None = Query(None, ge=0),
    annual_ytd: bool = Query(False),
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        _reject_legacy_week_start(request)
        report = query.query(
            start_date,
            end_date,
            promotion_count=promotion_count,
            inquiry_count=inquiry_count,
            annual_ytd=annual_ytd,
        )
        workbook_bytes = export_weekly_operations_report(report)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_operations_report_export_invalid",
            "起日不得晚於迄日。",
            "weekly-operations-report-export",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_operations_report_export_internal_error",
            "營運報表匯出失敗。",
            "weekly-operations-report-export",
        ) from exc
    filename = f"operations-report-{report.start_date}_{report.end_date}.xlsx"
    return StreamingResponse(
        iter([workbook_bytes]),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _case_row_view_dict(row) -> dict[str, object]:
    return {
        "case_no": row.case_no,
        "applicant_name": row.applicant_name,
        "application_date": row.application_date,
        "identity_status": row.identity_status,
        "review_result": row.review_result,
        "order_status": row.order_status,
        "service_days": row.service_days,
        "service_hours_per_day": row.service_hours_per_day,
        "planned_start_date": row.planned_start_date,
        "planned_end_date": row.planned_end_date,
        "district": row.district,
        "data_quality_codes": list(row.data_quality_codes),
    }


def _subsidy_row_view_dict(row) -> dict[str, object]:
    return {
        "serial_number": row.serial_number,
        "case_no": row.case_no,
        "eligibility": row.eligibility,
        "service_start": row.service_start,
        "service_end": row.service_end,
        "subsidy_hours": row.subsidy_hours,
        "subsidy_days": row.subsidy_days,
        "service_days": row.service_days,
        "subsidy_amount_ntd": row.subsidy_amount_ntd,
        "unit_price_ntd": row.unit_price_ntd,
        "employer_name": row.employer_name,
        "staff_name": row.staff_name,
        "identity_card": row.identity_card,
        "address": row.address,
    }


def _service_row_view_dict(row) -> dict[str, object]:
    return {
        "assignment_id": row.assignment_id,
        "case_no": row.case_no,
        "client_name": row.client_name,
        "staff_name": row.staff_name,
        "service_start_date": row.service_start_date,
        "service_end_date": row.service_end_date,
        "period_start_date": row.period_start_date,
        "period_end_date": row.period_end_date,
        "service_hours_per_day": row.service_hours_per_day,
        "weekly_work_days": row.weekly_work_days,
        "weekly_hours": row.weekly_hours,
        "order_status": row.order_status,
        "completed": row.completed,
        "data_quality_codes": list(row.data_quality_codes),
    }


def _weekly_report_view(report) -> WeeklyOperationsReportView:
    return WeeklyOperationsReportView.model_validate(
        {
            "schema_version": report.schema_version,
            "period": {
                "start_date": report.start_date,
                "end_date": report.end_date,
                "timezone": report.timezone,
                "period_label": report.period_label,
            },
            "generated_at": report.generated_at,
            "source_revision": report.source_revision,
            "summary": _slots_dict(report.summary),
            "case_rows": [_case_row_view_dict(row) for row in report.case_rows],
            "subsidy_partitions": [
                {
                    "citizen_kind": partition.citizen_kind,
                    "row_count": len(partition.rows),
                    "total_amount_ntd": sum(row.subsidy_amount_ntd for row in partition.rows),
                    "rows": [_subsidy_row_view_dict(row) for row in partition.rows],
                }
                for partition in report.subsidy_partitions
            ],
            "service_rows": [_service_row_view_dict(row) for row in report.service_rows],
            "data_quality_issues": [_slots_dict(issue) for issue in report.data_quality_issues],
        },
    )


def _reject_legacy_week_start(request: Request) -> None:
    if "week_start" in request.query_params:
        raise ValueError("weekly_operations_report_legacy_week_start")


def _slots_dict(value) -> dict[str, object]:
    return {
        field: list(item) if isinstance(item := getattr(value, field), tuple) else item
        for field in value.__dataclass_fields__
    }


@router.get(
    "/weekly/batches",
    response_model=BaseResponse[list[WeeklyBatchView]],
)
def list_weekly_batches(
    year: int = Query(..., ge=1912),
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportBatchService = Depends(get_weekly_report_batch_service),
):
    del principal
    try:
        batches = service.list_batches(year)
        return BaseResponse(
            data=[
                WeeklyBatchView(
                    id=b.id,
                    year=b.year,
                    week_code=b.week_code,
                    cutoff_at=b.cutoff_at,
                    promotion_count=b.promotion_count,
                    inquiry_count=b.inquiry_count,
                    notes=b.notes,
                    case_count=b.case_count,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                )
                for b in batches
            ]
        )
    except Exception as exc:
        raise internal_query_error(
            "weekly_batch_list_failed", "週報批次清單查詢失敗。", "weekly-batches"
        ) from exc


@router.get(
    "/weekly/unclosed-cases",
    response_model=BaseResponse[list[UnclosedCaseView]],
)
def list_unclosed_cases(
    year: int | None = Query(None, ge=1912),
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportBatchService = Depends(get_weekly_report_batch_service),
):
    del principal
    try:
        cases = service.get_unclosed_cases(year)
        return BaseResponse(
            data=[
                UnclosedCaseView(
                    case_no=c.case_no,
                    applicant_name=c.applicant_name,
                    created_at=c.created_at,
                    order_status=c.order_status,
                    service_days=c.service_days,
                    service_hours_per_day=c.service_hours_per_day,
                )
                for c in cases
            ]
        )
    except Exception as exc:
        raise internal_query_error(
            "unclosed_cases_query_failed", "未結算案件查詢失敗。", "unclosed-cases"
        ) from exc


@router.post(
    "/weekly/batches",
    response_model=BaseResponse[WeeklyBatchView],
)
def close_weekly_batch(
    payload: CloseWeeklyBatchRequest,
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportBatchService = Depends(get_weekly_report_batch_service),
):
    del principal
    try:
        batch = service.close_batch(
            year=payload.year,
            week_code=payload.week_code,
            promotion_count=payload.promotion_count,
            inquiry_count=payload.inquiry_count,
            case_nos=payload.case_nos,
            notes=payload.notes,
        )
        return BaseResponse(
            data=WeeklyBatchView(
                id=batch.id,
                year=batch.year,
                week_code=batch.week_code,
                cutoff_at=batch.cutoff_at,
                promotion_count=batch.promotion_count,
                inquiry_count=batch.inquiry_count,
                notes=batch.notes,
                case_count=batch.case_count,
                created_at=batch.created_at,
                updated_at=batch.updated_at,
            )
        )
    except Exception as exc:
        raise internal_query_error(
            "weekly_batch_close_failed", "週報結算失敗。", "weekly-batches"
        ) from exc


@router.patch(
    "/weekly/batches/{batch_id}",
    response_model=BaseResponse[WeeklyBatchView],
)
def update_weekly_batch_metrics(
    batch_id: int,
    payload: UpdateWeeklyBatchRequest,
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportBatchService = Depends(get_weekly_report_batch_service),
):
    del principal
    try:
        batch = service.update_batch_metrics(
            batch_id=batch_id,
            promotion_count=payload.promotion_count,
            inquiry_count=payload.inquiry_count,
            week_code=payload.week_code,
            notes=payload.notes,
        )
        return BaseResponse(
            data=WeeklyBatchView(
                id=batch.id,
                year=batch.year,
                week_code=batch.week_code,
                cutoff_at=batch.cutoff_at,
                promotion_count=batch.promotion_count,
                inquiry_count=batch.inquiry_count,
                notes=batch.notes,
                case_count=batch.case_count,
                created_at=batch.created_at,
                updated_at=batch.updated_at,
            )
        )
    except ValueError as exc:
        raise typed_http_error(404, "not_found", "batch_not_found", "找不到指定的週報批次。", "weekly-batches") from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_batch_update_failed", "週報批次指標更新失敗。", "weekly-batches"
        ) from exc


__all__ = ["router"]
