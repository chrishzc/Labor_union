"""Authenticated bank archive downloads and bounded case accounting commands."""
from dataclasses import asdict
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from openpyxl import Workbook
from pymysql import MySQLError

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace, get_statement_archive_application, get_monthly_accounting_query
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.finance_import import (
    AccountingWarningBody, CaseAccountingView, ManualStatementBody,
    StatementCommandReceiptView, StatementDuplicateBody,
)
from domains.finance_import.statement_archive import STATEMENT_COLUMNS
from subsystems.finance_import.accounting_workspace import AccountingConflict, AccountingWarning
from subsystems.finance_import.accounting_workspace import HistoricalAccountingMarker
from subsystems.finance_import.monthly_accounting import MonthlyAccountingReport, MonthlyAccountingUnavailable, ReceivableAccountingList
from subsystems.finance_import.statement_archive import StatementCommandConflict

router = APIRouter()


def _error(error):
    if isinstance(error, MonthlyAccountingUnavailable):
        return typed_http_error(503, "unavailable", "accounting_scope_unavailable", "部分銀行款跨統計範圍，尚缺正式分配金額，無法提供正確合計。請調整案件類別或核對原始款項。", "finance-workspace")
    if isinstance(error, ValueError) and str(error).startswith("invalid_accounting_"):
        return typed_http_error(422, "validation", "invalid_accounting_range", "請選擇有效的起訖月份、案件類別及統計口徑，起始月份不可晚於結束月份。", "finance-workspace")
    if isinstance(error, (AccountingConflict, StatementCommandConflict)):
        return typed_http_error(409, "conflict", "accounting_source_changed", "資料已變更，請重新整理後再確認。", "finance-workspace")
    if isinstance(error, LookupError):
        return typed_http_error(404, "not_found", "accounting_case_not_found", "找不到案件。", "finance-workspace")
    if isinstance(error, MySQLError):
        return typed_http_error(503, "unavailable", "accounting_unavailable", "帳務資料暫時無法取得，請稍後重試。", "finance-workspace")
    return typed_http_error(422, "validation", "invalid_statement_command", "請檢查交易日、單一收支金額、銷帳編號或備註及指定的明細。", "finance-workspace")


def _actor(principal):
    return f"admin_user_id:{principal.id}" if principal.id is not None else principal.username


def _case_view(case):
    payload = asdict(case)
    for field in ("client_items", "staff_items", "transactions", "warnings"):
        payload[field] = list(payload[field])
    for field in ("client_items", "staff_items"):
        for item, projected in zip(getattr(case, field), payload[field]):
            projected.update(remaining_ntd=item.remaining_ntd, noncash_ntd=item.noncash_ntd)
    payload["bank_facts"] = [
        {**bank, "cases": list(bank["cases"])} for bank in payload["bank_facts"]
    ]
    if payload["historical_marker"] is not None:
        payload["historical_marker"]["amounts"] = list(payload["historical_marker"]["amounts"])
    return CaseAccountingView(**payload)


class HistoricalAccountingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_unverifiable: StrictBool
    reason: str = Field(min_length=1, max_length=500)
    source_versions: dict[str, str]


@router.get("/accounting/receivables", response_model=BaseResponse[ReceivableAccountingList])
def receivable_items(due_month: str | None = None, category: str = "subsidy", undated_only: bool = False,
                     principal=Depends(require_admin), application=Depends(get_monthly_accounting_query)):
    del principal
    try:
        return BaseResponse(data=application.receivables(due_month, category, undated_only=undated_only), message="成功取得應收款項")
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/accounting/monthly", response_model=BaseResponse[MonthlyAccountingReport])
def monthly_accounting(start_month: str, end_month: str, category: str = "subsidy",
                       principal=Depends(require_admin), application=Depends(get_monthly_accounting_query)):
    del principal
    try:
        return BaseResponse(data=application.query(start_month, end_month, category), message="成功取得每月帳務")
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/accounting/monthly/export")
def export_monthly_accounting(start_month: str, end_month: str, category: str = "subsidy", basis: str = "due",
                              principal=Depends(require_admin), application=Depends(get_monthly_accounting_query)):
    del principal
    try:
        if basis not in {"due", "cash"}:
            raise ValueError("invalid_accounting_basis")
        report = application.query(start_month, end_month, category)
        if basis == "cash" and report.cash_unavailable_reason:
            raise MonthlyAccountingUnavailable(report.cash_unavailable_reason)
        book = Workbook()
        sheet = book.active
        sheet.title = "到期款進度" if basis == "due" else "實際收支"
        sheet.append(["月份", "應收", "已收", "收款其他處理", "待收", "應付", "已付", "付款其他處理", "待付", "應收減應付"] if basis == "due" else ["月份", "實際入款", "實際出款", "收支差額"])
        totals = [0] * (9 if basis == "due" else 3)
        for row in report.rows:
            values = [row.expected_in_ntd, row.received_ntd, row.other_in_ntd, row.remaining_in_ntd, row.expected_out_ntd,
                      row.paid_ntd, row.other_out_ntd, row.remaining_out_ntd, row.expected_in_ntd - row.expected_out_ntd] if basis == "due" else [row.cash_in_ntd, row.cash_out_ntd, row.cash_in_ntd - row.cash_out_ntd]
            sheet.append([row.month, *values])
            totals = [left + right for left, right in zip(totals, values)]
        sheet.append(["合計", *totals])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.column_dimensions['A'].width = 18
        for column in sheet.iter_cols(min_col=2):
            sheet.column_dimensions[column[0].column_letter].width = 18
            for cell in column[1:]:
                cell.number_format = '#,##0'
        scope = book.create_sheet("統計口徑")
        for row in (("起始月份", report.start_month), ("結束月份", report.end_month),
                    ("案件類別", {"subsidy":"補助案件","non_citizen":"非市民案件","all":"全部案件"}[report.category]),
                    ("資料截至", report.as_of),
                    ("統計方式", "依正式到期月份統計客戶應收、薪資及客戶退款；政府整期待收由整期帳務另查。" if basis == "due" else "依已正式核銷的銀行收付月份，單筆銀行來源只計一次；代墊回收不重複列收入。"),
                    ("歷史人工核銷", f"{len(report.excluded_cases)} 案，整案排除金額統計"),
                    ("未定到期日款項", f"{report.undated_item_count} 筆，未分入月份")):
            scope.append(row)
        scope.column_dimensions['A'].width = 24
        scope.column_dimensions['B'].width = 95
        recognized=book.create_sheet('差額認列（確認月份）')
        recognized.append(['確認月份','關聯案件','處理方式','非現金金額'])
        labels={'loss':'確認收不回，記錄損失','reduce_service_fee':'同意減收服務費','union_bank_fee':'由工會負擔手續費','absorb_overpayment':'工會承擔超付款，不再追回'}
        if report.recognition_unavailable_reason:
            recognized.append(['跨統計範圍，尚缺各案正式分配金額，不提供拆分合計'])
        else:
            for event in report.recognitions:
                recognized.append([event.confirmed_on[:7],'、'.join(event.cases),labels.get(event.action,event.action),event.amount_ntd])
        for column in ('A','B','C','D'):recognized.column_dimensions[column].width=32
        scope.append(['差額認列月份','依人員實際確認處理的月份列示，與原到期月份、銀行實收付月份分開，不增加銀行現金。'])
        content = BytesIO()
        book.save(content)
        return Response(content.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="monthly-accounting.xlsx"', "Cache-Control": "no-store"})
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/cases/{case_no}/accounting/historical-marker", response_model=BaseResponse[HistoricalAccountingMarker | None])
def historical_marker(case_no: str, principal=Depends(require_admin), application=Depends(get_accounting_workspace)):
    del principal
    try:
        application.state.case_client(case_no)
        return BaseResponse(data=application.state.marker(case_no), message="成功取得案件人工核銷標記")
    except (LookupError, ValueError, MySQLError) as error:
        raise _error(error) from None


@router.post("/cases/{case_no}/accounting/historical-marker", response_model=BaseResponse[HistoricalAccountingMarker])
def mark_historical_accounting(case_no: str, body: HistoricalAccountingBody,
                               idempotency_key: Annotated[str, Header(min_length=1, max_length=191)],
                               principal=Depends(require_admin), application=Depends(get_accounting_workspace)):
    try:
        if body.confirmed_unverifiable is not True:
            raise ValueError("historical_accounting_confirmation_required")
        marker = application.mark_historical(case_no, body.reason, body.source_versions, idempotency_key, _actor(principal))
        return BaseResponse(data=marker, message="案件帳務已人工核銷；原始金額保留")
    except (LookupError, ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/statements/export")
def export_statements(principal=Depends(require_admin), application=Depends(get_statement_archive_application)):
    del principal
    try:
        rows = application.export_rows()
        workbook = Workbook()
        workbook.remove(workbook.active)
        banks = sorted({row.bank for row in rows}) or ["manual"]
        labels = {"sinopac": "永豐", "taishin": "台新", "legacy": "歷史格式", "manual": "人工新增"}
        for bank in banks:
            selected = [row for row in rows if row.bank == bank]
            columns = list(STATEMENT_COLUMNS) if bank in {"sinopac", "manual"} else []
            for row in selected:
                for name, _ in row.fields:
                    if name not in columns:
                        columns.append(name)
            metadata = []
            for name in ("明細識別", "資料來源", "關聯案件"):
                while name in columns:
                    name = "_" + name
                metadata.append(name)
            sheet = workbook.create_sheet(labels.get(bank, bank) if rows else "無成功明細（0筆）")
            sheet.append([*columns, *metadata])
            for cell in sheet[1]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
            for row in selected:
                fields = dict(row.fields)
                values = [fields.get(column) for column in columns] + [row.identity, row.source, ",".join(row.cases)]
                sheet.append(values)
                # Bank text is untrusted spreadsheet content, never a formula.
                for cell in sheet[sheet.max_row]:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
        content = BytesIO()
        workbook.save(content)
        return Response(content.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": 'attachment; filename="bank-statements.xlsx"',
            "X-Statement-Count": str(len(rows)), "Cache-Control": "no-store",
        })
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.post("/statements/manual", response_model=BaseResponse[StatementCommandReceiptView])
def create_manual_statement(
    body: ManualStatementBody,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=191)],
    principal=Depends(require_admin), application=Depends(get_statement_archive_application),
):
    try:
        result = application.create_manual(body.fields, idempotency_key, _actor(principal), body.duplicate_of)
        return BaseResponse(data=StatementCommandReceiptView(**asdict(result)), message="重複明細已排除" if result.excluded_count else "人工明細已保存")
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.post("/statements/duplicates", response_model=BaseResponse[StatementCommandReceiptView])
def exclude_statement_duplicate(
    body: StatementDuplicateBody,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=191)],
    principal=Depends(require_admin), application=Depends(get_statement_archive_application),
):
    try:
        result = application.exclude_duplicate(body.candidate_identity, body.kept_identity, idempotency_key, _actor(principal))
        return BaseResponse(data=StatementCommandReceiptView(**asdict(result)), message="重複明細已排除，保留既存明細")
    except (ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/cases/{case_no}/accounting", response_model=BaseResponse[CaseAccountingView])
def case_accounting(case_no: str, principal=Depends(require_admin), application=Depends(get_accounting_workspace)):
    del principal
    try:
        return BaseResponse(data=_case_view(application.query(case_no)), message="成功取得案件帳務")
    except (LookupError, ValueError, MySQLError) as error:
        raise _error(error) from None


@router.get("/accounting/warnings", response_model=BaseResponse[list[CaseAccountingView]])
def accounting_warnings(principal=Depends(require_admin), application=Depends(get_accounting_workspace)):
    del principal
    try:
        return BaseResponse(data=[_case_view(case) for case in application.warnings()], message="成功取得帳務警示")
    except (LookupError, ValueError, MySQLError) as error:
        raise _error(error) from None


@router.post("/cases/{case_no}/accounting/dismiss", response_model=BaseResponse[CaseAccountingView])
def dismiss_accounting_warning(body: AccountingWarningBody, case_no: str, principal=Depends(require_admin), application=Depends(get_accounting_workspace)):
    try:
        result = application.dismiss(case_no, AccountingWarning(**body.model_dump()), _actor(principal))
        return BaseResponse(data=_case_view(result), message="帳務警示已解除")
    except (LookupError, ValueError, MySQLError) as error:
        raise _error(error) from None
