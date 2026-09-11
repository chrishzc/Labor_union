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
    get_weekly_report_metrics_service,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.operations_reports import (
    SaveWeeklyReportMetricRequest,
    WeeklyOperationsReportView,
    WeeklyReportMetricView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.reporting.weekly_operations_report_export import export_weekly_operations_report
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery
from subsystems.reporting.weekly_report_metrics_service import WeeklyReportMetricsService


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
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        _reject_retired_weekly_parameters(request)
        report = query.query(start_date, end_date)
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
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        _reject_retired_weekly_parameters(request)
        report = query.query(start_date, end_date)
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
        "week_start_date": row.week_start_date,
        "week_end_date": row.week_end_date,
        "week_label": row.week_label,
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
        "application_roc_year": row.application_roc_year,
        "claim_period_label": row.claim_period_label,
        "reconciliation_status": row.reconciliation_status,
        "notes": row.notes,
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
            "weekly_metrics": [_slots_dict(metric) for metric in report.weekly_metrics],
            "data_quality_issues": [_slots_dict(issue) for issue in report.data_quality_issues],
        },
    )


def _reject_retired_weekly_parameters(request: Request) -> None:
    retired = {"week_start", "promotion_count", "inquiry_count", "annual_ytd"}
    if retired.intersection(request.query_params):
        raise ValueError("weekly_operations_report_retired_parameter")


def _slots_dict(value) -> dict[str, object]:
    return {
        field: list(item) if isinstance(item := getattr(value, field), tuple) else item
        for field in value.__dataclass_fields__
    }


@router.get(
    "/weekly/metrics",
    response_model=BaseResponse[list[WeeklyReportMetricView]],
)
def list_weekly_report_metrics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportMetricsService = Depends(get_weekly_report_metrics_service),
):
    del principal
    try:
        return BaseResponse(
            data=[WeeklyReportMetricView.model_validate(_slots_dict(metric)) for metric in service.list_metrics(start_date, end_date)]
        )
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_report_metric_range_invalid",
            "起日不得晚於迄日。",
            "weekly-report-metrics",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_report_metrics_query_failed",
            "每週推廣與詢問數值查詢失敗。",
            "weekly-report-metrics",
        ) from exc


@router.put(
    "/weekly/metrics/{week_start_date}",
    response_model=BaseResponse[WeeklyReportMetricView],
)
def save_weekly_report_metric(
    week_start_date: date,
    payload: SaveWeeklyReportMetricRequest,
    principal: AdminPrincipal = Depends(require_admin),
    service: WeeklyReportMetricsService = Depends(get_weekly_report_metrics_service),
):
    del principal
    try:
        metric = service.save_metric(
            week_start_date=week_start_date,
            promotion_count=payload.promotion_count,
            inquiry_count=payload.inquiry_count,
        )
        return BaseResponse(data=WeeklyReportMetricView.model_validate(_slots_dict(metric)))
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_report_metric_invalid",
            "週起日必須是星期一，且數值不得小於零。",
            "weekly-report-metrics",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_report_metric_save_failed",
            "每週推廣與詢問數值儲存失敗。",
            "weekly-report-metrics",
        ) from exc


__all__ = ["router"]
