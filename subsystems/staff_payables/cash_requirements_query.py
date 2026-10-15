"""Read-only cash planning from current payable and arranged-service facts."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol

from domains.client_finance.subsidy_advance import subsidy_advance_due_date
from domains.client_finance.subsidy_return_projection import project_subsidy_return
from subsystems.staff_payables.accounts_payable_export import CaseStaffPayableAuditItem

PaymentKind = Literal["staff_payable", "client_refund", "client_subsidy_return"]


@dataclass(frozen=True, slots=True)
class CashRefundFact:
    identity: str
    kind: PaymentKind
    amount_ntd: int
    payment_date: date | None
    recipient_name: str
    recipient_ready: bool


@dataclass(frozen=True, slots=True)
class CashRequirementCase:
    case_no: str
    client_name: str
    order_status: str
    has_arrangement: bool
    planned_end_date: date | None
    identity_status: str
    service_hours: Decimal | None
    floor_fee: Decimal | None
    client_hourly_rate_ntd: int | None
    service_fees_collected: bool | None
    has_subsidy_return: bool
    staff_items: tuple[CaseStaffPayableAuditItem, ...]
    refunds: tuple[CashRefundFact, ...]


@dataclass(frozen=True, slots=True)
class CashRequirementRow:
    row_id: str
    case_no: str
    recipient_name: str | None
    payment_type: PaymentKind
    certainty: Literal["estimated", "confirmed"]
    source: Literal["staff_obligation", "historical_payroll", "missing_payroll", "client_refund", "subsidy_estimate"]
    source_amount_ntd: int | None
    unpaid_amount_ntd: int | None
    payment_date: date | None
    date_is_estimate: bool
    pending_reasons: tuple[str, ...]
    staff_id: int | None = None


@dataclass(frozen=True, slots=True)
class CashRequirementPage:
    rows: tuple[CashRequirementRow, ...]
    next_cursor: str | None


class CashRequirementsRepository(Protocol):
    def query_cases(self, after_case_no: str | None, limit: int) -> tuple[CashRequirementCase, ...]: ...


def query_cash_requirements(repository: CashRequirementsRepository, *, page_size: int = 100,
                            after_case_no: str | None = None) -> CashRequirementPage:
    if isinstance(page_size, bool) or not 1 <= page_size <= 200:
        raise ValueError("cash_requirements_page_size_invalid")
    facts = repository.query_cases(after_case_no, page_size + 1)
    rows = tuple(row for case in facts[:page_size] for row in _case_rows(case))
    return CashRequirementPage(rows, facts[page_size - 1].case_no if len(facts) > page_size else None)


def _case_rows(case: CashRequirementCase) -> tuple[CashRequirementRow, ...]:
    rows = []
    for item in case.staff_items:
        if item.disposition == "paid_or_settled" or (item.balance is not None and item.balance.amount <= 0):
            continue
        if not case.has_arrangement and item.source == "order_facts":
            continue
        reasons = []
        if item.amount_due is None:
            reasons.append("月嫂應付金額缺少計算依據，待確認")
        if item.effective_due_date is None:
            reasons.append("月嫂付款日尚未確定")
        if item.disposition == "blocked":
            reasons.append("月嫂付款狀態或受款資料待確認")
        source = {"formal_obligation": "staff_obligation", "historical_projection": "historical_payroll", "order_facts": "missing_payroll"}[item.source]
        rows.append(CashRequirementRow(
            item.obligation_identity or f"{case.case_no}:staff:{item.staff_id or 'unknown'}", case.case_no, item.recipient_name,
            "staff_payable", "confirmed" if item.source == "formal_obligation" else "estimated", source,
            None if item.amount_due is None else item.amount_due.amount,
            None if item.balance is None else item.balance.amount, item.effective_due_date, False, tuple(reasons), item.staff_id,
        ))
    for refund in case.refunds:
        if refund.amount_ntd <= 0:
            continue
        reasons = []
        if refund.payment_date is None:
            reasons.append("退款付款日尚未確定")
        if not refund.recipient_ready:
            reasons.append("退款收款資料待確認")
        rows.append(CashRequirementRow(refund.identity, case.case_no, refund.recipient_name,
            refund.kind, "confirmed", "client_refund", refund.amount_ntd, refund.amount_ntd,
            refund.payment_date, False, tuple(reasons)))
    if case.has_subsidy_return or not case.has_arrangement or case.order_status == "訂單取消":
        return tuple(rows)
    projection = project_subsidy_return(
        identity_status=case.identity_status, service_hours=case.service_hours, floor_fee=case.floor_fee,
        client_hourly_rate_ntd=case.client_hourly_rate_ntd, completed_on=None,
        has_formal_return=False, formal_amount_ntd=None, formal_due_date=None, return_settled=False,
    )
    if projection is None or projection.amount_ntd == 0:
        return tuple(rows)
    reasons = ["客戶補助退款單尚未建立"]
    if case.order_status not in {"訂單完成", "歷史訂單－服務完成", "歷史訂單－帳務完成"}:
        reasons.append("服務尚未完成")
    if case.service_fees_collected is not True:
        reasons.append("客戶服務費尚未收齊" if case.service_fees_collected is False else "客戶服務費收款狀態待確認")
    if projection.amount_ntd is None:
        reasons.append("補助退款金額缺少服務量、費用或凍結單價，待確認")
    due_date = subsidy_advance_due_date(case.planned_end_date) if case.planned_end_date else None
    if due_date is None:
        reasons.append("預計服務結束日尚未確定")
    rows.append(CashRequirementRow(f"{case.case_no}:subsidy:estimate", case.case_no, case.client_name,
        "client_subsidy_return", "estimated", "subsidy_estimate", projection.amount_ntd,
        projection.amount_ntd, due_date, due_date is not None, tuple(reasons)))
    return tuple(rows)
