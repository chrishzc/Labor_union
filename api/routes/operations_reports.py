"""
File: operations_reports.py
Description: 提供營運週報 strict JSON Query 與同 candidate 的三分頁 XLSX 匯出。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
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
    week_start: date = Query(...),
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        report = query.query(week_start)
        view = _weekly_report_view(report)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_operations_report_invalid",
            "週起日必須是有效的星期一。",
            "weekly-operations-report",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_operations_report_internal_error",
            "營運週報查詢失敗。",
            "weekly-operations-report",
        ) from exc
    return BaseResponse(data=view, message="Weekly operations report")


@router.get("/weekly/export")
def export_weekly_operations_report_xlsx(
    week_start: date = Query(...),
    principal: AdminPrincipal = Depends(require_admin),
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    del principal
    try:
        report = query.query(week_start)
        workbook_bytes = export_weekly_operations_report(report)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "weekly_operations_report_export_invalid",
            "週起日必須是有效的星期一。",
            "weekly-operations-report-export",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "weekly_operations_report_export_internal_error",
            "營運週報匯出失敗。",
            "weekly-operations-report-export",
        ) from exc
    filename = f"weekly-operations-report-{report.week_start}_{report.week_end}.xlsx"
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
                "week_start": report.week_start,
                "week_end": report.week_end,
                "timezone": report.timezone,
                "week_label": report.week_label,
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


def _slots_dict(value) -> dict[str, object]:
    return {
        field: list(item) if isinstance(item := getattr(value, field), tuple) else item
        for field in value.__dataclass_fields__
    }


__all__ = ["router"]
