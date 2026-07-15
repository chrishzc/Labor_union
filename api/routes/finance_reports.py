"""Read-only finance report endpoints for the management UI."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.schemas.base import BaseResponse
from services import accounts_payable_export
from services import subsidy_reconciliation_register


router = APIRouter(prefix="/api/v1/finance-reports", tags=["Finance Reports"])


def _payable_preview(target_month: str) -> dict[str, Any]:
    report = accounts_payable_export.build_accounts_payable_export(target_month)
    json_rows = []
    for row in report["payable_rows"]:
        json_rows.append({
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in row.items()
        })
    return {
        "payable_rows": json_rows,
        "bank_totals": {
            code: float(total) if isinstance(total, Decimal) else total
            for code, total in report["bank_totals"].items()
        },
    }


def _xlsx_response(workbook_bytes: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([workbook_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/accounts-payable", response_model=BaseResponse[dict[str, Any]])
def preview_accounts_payable(
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    """Return the monthly transfer preview without workbook bytes."""
    try:
        return BaseResponse(data=_payable_preview(target_month), message="Accounts payable preview")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/accounts-payable/export")
def export_accounts_payable(
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    """Download the monthly transfer workbook, including subsidy-return rows."""
    try:
        report = accounts_payable_export.build_accounts_payable_export(target_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _xlsx_response(report["xlsx_bytes"], f"accounts-payable-{target_month}.xlsx")


@router.get("/subsidy-reconciliation/quarterly", response_model=BaseResponse[dict[str, Any]])
def preview_quarterly_reconciliation(
    application_year: int = Query(..., ge=1912),
    quarter: int = Query(..., ge=1, le=4),
):
    """Return the selected quarterly reconciliation register without workbook bytes."""
    try:
        report = subsidy_reconciliation_register.build_quarterly_subsidy_register(
            application_year, quarter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BaseResponse(
        data={key: value for key, value in report.items() if key != "xlsx_bytes"},
        message="Quarterly subsidy reconciliation preview",
    )


@router.get("/subsidy-reconciliation/quarterly/export")
def export_quarterly_reconciliation(
    application_year: int = Query(..., ge=1912),
    quarter: int = Query(..., ge=1, le=4),
):
    """Download the selected quarterly reconciliation register."""
    try:
        report = subsidy_reconciliation_register.build_quarterly_subsidy_register(
            application_year, quarter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _xlsx_response(report["xlsx_bytes"], f"subsidy-reconciliation-{application_year}-Q{quarter}.xlsx")


@router.get("/subsidy-reconciliation/annual", response_model=BaseResponse[dict[str, Any]])
def preview_annual_reconciliation(
    application_year: int = Query(..., ge=1912),
):
    """Return the selected annual subsidy summary without workbook bytes."""
    try:
        report = subsidy_reconciliation_register.build_annual_subsidy_summary(application_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BaseResponse(
        data={key: value for key, value in report.items() if key != "xlsx_bytes"},
        message="Annual subsidy reconciliation preview",
    )


@router.get("/subsidy-reconciliation/annual/export")
def export_annual_reconciliation(
    application_year: int = Query(..., ge=1912),
):
    """Download the selected annual subsidy summary."""
    try:
        report = subsidy_reconciliation_register.build_annual_subsidy_summary(application_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _xlsx_response(report["xlsx_bytes"], f"subsidy-reconciliation-{application_year}.xlsx")
