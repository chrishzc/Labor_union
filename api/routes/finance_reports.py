"""Read-only finance report endpoints for the management UI."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.dependencies.accounts_payable_export import (
    AccountsPayableExportApplication,
    get_accounts_payable_export_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.accounts_payable_export import (
    AccountsPayableArchiveView,
    AccountsPayablePreviewView,
)
from subsystems.government_subsidy import reconciliation_register_query


router = APIRouter(prefix="/api/v1/finance-reports", tags=["Finance Reports"])
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class XlsxStreamingResponse(StreamingResponse):
    media_type = XLSX_MEDIA_TYPE


def _xlsx_response(workbook_bytes: bytes, filename: str) -> XlsxStreamingResponse:
    return XlsxStreamingResponse(
        iter([workbook_bytes]),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/accounts-payable",
    response_model=BaseResponse[AccountsPayablePreviewView],
)
def preview_accounts_payable(
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    view: str = Query("summary", pattern=r"^(summary|export)$"),
    application: AccountsPayableExportApplication = Depends(
        get_accounts_payable_export_application
    ),
):
    """Return the current payable rows for the selected payment date."""
    del view
    try:
        target_payment_date = _target_payment_date(target_month)
        rows = application.query(target_payment_date)
        preview = _accounts_payable_preview(target_payment_date, rows)
        return BaseResponse(
            data=preview,
            message="Accounts payable export preview",
        )
    except (TypeError, ValueError) as exc:
        raise typed_http_error(
            400,
            "validation",
            "accounts_payable_query_invalid",
            "應付帳款查詢條件無效。",
            "accounts-payable-query",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "accounts_payable_query_internal_error",
            "應付帳款查詢失敗。",
            "accounts-payable-query",
        ) from exc


@router.get("/accounts-payable-summary", response_model=BaseResponse[dict[str, Any]])
def preview_accounts_payable_summary(
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    view: str = Query("summary", pattern=r"^(summary|export)$"),
):
    """Return accounts-payable output.\n\n    - view=summary (default): completed-case summary rows for payment status overview.\n    - view=export: transfer export rows in the fixed 9-column specification.\n    """
    del target_month, view
    raise HTTPException(
        status_code=410,
        detail="legacy_accounts_payable_summary_removed",
    )


@router.get("/accounts-payable/export", response_class=XlsxStreamingResponse)
def export_accounts_payable(
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    application: AccountsPayableExportApplication = Depends(
        get_accounts_payable_export_application
    ),
):
    """Archive and download the exact same accounts-payable workbook bytes."""
    try:
        receipt = application.export(_target_payment_date(target_month))
    except (TypeError, ValueError) as exc:
        raise typed_http_error(
            400,
            "validation",
            "accounts_payable_export_invalid",
            "應付帳款匯出條件無效。",
            "accounts-payable-export",
        ) from exc
    except (FileExistsError, OSError, RuntimeError) as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "accounts_payable_archive_failed",
            "應付帳款檔案暫時無法封存，請稍後以相同條件重試。",
            "accounts-payable-export",
            retryable=True,
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "accounts_payable_export_internal_error",
            "應付帳款匯出失敗。",
            "accounts-payable-export",
        ) from exc
    return _xlsx_response(receipt.workbook_bytes, receipt.filename)


@router.get(
    "/accounts-payable/archive",
    response_model=BaseResponse[AccountsPayableArchiveView],
)
def query_accounts_payable_archive(
    year: int = Query(..., ge=2000, le=9999),
    application: AccountsPayableExportApplication = Depends(
        get_accounts_payable_export_application
    ),
):
    try:
        records = application.query_archive(year)
        return BaseResponse(
            data=_archive_view(year, records),
            message="Accounts payable archive",
        )
    except Exception as exc:
        raise internal_query_error(
            "accounts_payable_archive_query_internal_error",
            "應付帳款封存檔查詢失敗。",
            "accounts-payable-archive-query",
        ) from exc


def _archive_view(year, records) -> AccountsPayableArchiveView:
    return AccountsPayableArchiveView(
        year=year,
        records=[
            {
                "filename": item.filename,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in records
        ],
    )


def _target_payment_date(target_month: str) -> date:
    return date.fromisoformat(f"{target_month}-15")


def _accounts_payable_preview(target_payment_date, rows):
    return AccountsPayablePreviewView(
        target_payment_date=target_payment_date,
        row_count=len(rows),
        total_amount_ntd=sum(row.amount.amount for row in rows),
        rows=[_accounts_payable_row(row) for row in rows],
    )


def _accounts_payable_row(row) -> dict[str, object]:
    return {
        "payment_date": row.payment_date,
        "payment_type": row.payment_type,
        "recipient_name": row.recipient_name,
        "bank_code": row.bank_code,
        "bank_account": row.bank_account,
        "amount_ntd": row.amount.amount,
        "obligation_identities": list(row.obligation_identities),
        "case_numbers": list(row.case_numbers),
        "recipient_identity_card": row.recipient_identity_card,
    }


@router.get("/subsidy-reconciliation/quarterly", response_model=BaseResponse[dict[str, Any]])
def preview_quarterly_reconciliation(
    application_year: int = Query(..., ge=1912),
    quarter: int = Query(..., ge=1, le=4),
):
    """Return the selected quarterly reconciliation register without workbook bytes."""
    try:
        report = reconciliation_register_query.build_quarterly_subsidy_register(
            application_year, quarter,
        )
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "quarterly_subsidy_report_invalid",
            "季度補助核銷查詢條件無效。",
            "quarterly-subsidy-report",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "quarterly_subsidy_report_internal_error",
            "季度補助核銷查詢失敗。",
            "quarterly-subsidy-report",
        ) from exc
    return BaseResponse(
        data={key: value for key, value in report.items() if key != "xlsx_bytes"},
        message="Quarterly subsidy reconciliation preview",
    )


@router.get("/subsidy-reconciliation/quarterly/export", response_class=XlsxStreamingResponse)
def export_quarterly_reconciliation(
    application_year: int = Query(..., ge=1912),
    quarter: int = Query(..., ge=1, le=4),
):
    """Download the selected quarterly reconciliation register."""
    try:
        report = reconciliation_register_query.build_quarterly_subsidy_register(
            application_year, quarter,
        )
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "quarterly_subsidy_export_invalid",
            "季度補助核銷匯出條件無效。",
            "quarterly-subsidy-export",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "quarterly_subsidy_export_internal_error",
            "季度補助核銷匯出失敗。",
            "quarterly-subsidy-export",
        ) from exc
    return _xlsx_response(report["xlsx_bytes"], f"subsidy-reconciliation-{application_year}-Q{quarter}.xlsx")


@router.get("/subsidy-reconciliation/annual", response_model=BaseResponse[dict[str, Any]])
def preview_annual_reconciliation(
    application_year: int = Query(..., ge=1912),
):
    """Return the selected annual subsidy summary without workbook bytes."""
    try:
        report = reconciliation_register_query.build_annual_subsidy_summary(application_year)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "annual_subsidy_report_invalid",
            "年度補助核銷查詢條件無效。",
            "annual-subsidy-report",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "annual_subsidy_report_internal_error",
            "年度補助核銷查詢失敗。",
            "annual-subsidy-report",
        ) from exc
    return BaseResponse(
        data={key: value for key, value in report.items() if key != "xlsx_bytes"},
        message="Annual subsidy reconciliation preview",
    )


@router.get("/subsidy-reconciliation/annual/export", response_class=XlsxStreamingResponse)
def export_annual_reconciliation(
    application_year: int = Query(..., ge=1912),
):
    """Download the selected annual subsidy summary."""
    try:
        report = reconciliation_register_query.build_annual_subsidy_summary(application_year)
    except ValueError as exc:
        raise typed_http_error(
            400,
            "validation",
            "annual_subsidy_export_invalid",
            "年度補助核銷匯出條件無效。",
            "annual-subsidy-export",
        ) from exc
    except Exception as exc:
        raise internal_query_error(
            "annual_subsidy_export_internal_error",
            "年度補助核銷匯出失敗。",
            "annual-subsidy-export",
        ) from exc
    return _xlsx_response(report["xlsx_bytes"], f"subsidy-reconciliation-{application_year}.xlsx")
