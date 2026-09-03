"""
File: operations_reports.py
Description: 提供自選期間營運報表 strict JSON Query 與同 candidate 的三分頁 XLSX 匯出。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from api.dependencies.admin_auth import require_admin
from api.dependencies.operations_reports import get_weekly_operations_report_query
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.operations_reports import WeeklyOperationsReportView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.reporting.weekly_operations_report_export import export_weekly_operations_report
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery


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
        _reject_legacy_week_start(request)
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
        _reject_legacy_week_start(request)
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
            "case_rows": [_slots_dict(row) for row in report.case_rows],
            "subsidy_partitions": [
                {
                    "citizen_kind": partition.citizen_kind,
                    "row_count": len(partition.rows),
                    "total_amount_ntd": sum(row.subsidy_amount_ntd for row in partition.rows),
                    "rows": [_slots_dict(row) for row in partition.rows],
                }
                for partition in report.subsidy_partitions
            ],
            "service_rows": [_slots_dict(row) for row in report.service_rows],
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


__all__ = ["router"]
