"""Read-only month cohorts and unique, committed bank cash facts."""
from dataclasses import dataclass
from datetime import date, datetime
from shared_kernel.clock import TAIPEI_TIME_ZONE
from typing import Protocol

from subsystems.finance_import.accounting_workspace import CaseAccounting, AccountingBankFact


@dataclass(frozen=True)
class MonthlyAccountingItem:
    case_no: str
    client_name: str
    identity: str
    direction: str
    label: str
    party: str
    due_date: str | None
    expected_ntd: int
    actual_ntd: int
    noncash_ntd: int
    remaining_ntd: int


@dataclass(frozen=True)
class AccountingRecognition:
    identity: str
    cases: tuple[str,...]
    action: str
    amount_ntd: int
    confirmed_on: str


@dataclass(frozen=True)
class MonthlyAccountingRow:
    month: str
    expected_in_ntd: int
    received_ntd: int
    remaining_in_ntd: int
    expected_out_ntd: int
    paid_ntd: int
    remaining_out_ntd: int
    cash_in_ntd: int | None
    cash_out_ntd: int | None
    items: tuple[MonthlyAccountingItem, ...]
    bank_facts: tuple[AccountingBankFact, ...]
    other_in_ntd: int = 0
    other_out_ntd: int = 0
    cash_by_flow: dict[str, int] | None = None


@dataclass(frozen=True)
class MonthlyAccountingReport:
    start_month: str
    end_month: str
    category: str
    as_of: str
    rows: tuple[MonthlyAccountingRow, ...]
    excluded_cases: tuple[str, ...]
    undated_item_count: int
    cash_unavailable_reason: str | None = None
    recognitions: tuple[AccountingRecognition,...] = ()
    recognition_unavailable_reason: str | None = None


@dataclass(frozen=True)
class ReceivableAccountingList:
    due_month: str | None
    category: str
    items: tuple[MonthlyAccountingItem, ...]
    undated_count: int


class MonthlyAccountingSource(Protocol):
    def case_categories(self) -> dict[str, str]: ...
    def bank_facts(self, start: date, end: date) -> tuple[AccountingBankFact, ...]: ...
    def historical_markers(self) -> tuple[str, ...]: ...
    def reporting_cases(self, start: date, end: date) -> tuple[str, ...]: ...
    def recognitions(self, start: date, end: date) -> tuple[AccountingRecognition,...]: ...


class MonthlyAccountingUnavailable(ValueError):
    """The source cannot attribute a bank amount without inventing a split."""


def month_start(value: str) -> date:
    try:
        result = date.fromisoformat(value + "-01")
    except ValueError:
        raise ValueError("invalid_accounting_month") from None
    if result.strftime("%Y-%m") != value:
        raise ValueError("invalid_accounting_month")
    return result


class MonthlyAccountingQuery:
    def __init__(self, source: MonthlyAccountingSource, case_query):
        self.source, self.case_query = source, case_query

    def _items(self, start: date, end: date, category: str):
        if category not in {"all", "subsidy", "non_citizen"}:
            raise ValueError("invalid_accounting_category")
        categories = self.source.case_categories()
        excluded = frozenset(self.source.historical_markers())
        selected = {case for case, group in categories.items() if case not in excluded and (category == "all" or category == group)}
        dated, undated = [], []
        for case_no in sorted(selected & set(self.source.reporting_cases(start, end))):
            case: CaseAccounting = self.case_query(case_no)
            for item in (*case.client_items, *case.staff_items):
                if not getattr(item, "summary_included", True):
                    continue
                projected = MonthlyAccountingItem(case_no, case.client_name, item.identity, item.direction,
                    item.label, item.party, item.due_date, item.expected_ntd, item.actual_ntd, item.noncash_ntd, item.remaining_ntd)
                (undated if item.due_date is None else dated).append(projected)
        return selected, excluded, dated, undated

    def receivables(self, due_month: str | None, category: str, *, undated_only: bool = False):
        month = month_start(due_month) if due_month else None
        _, _, dated, undated = self._items(month or date.min, month or date(9999, 12, 1), category)
        rows = undated if undated_only else [item for item in dated if not due_month or item.due_date[:7] == due_month]
        return ReceivableAccountingList(due_month, category,
            tuple(sorted((item for item in rows if item.direction == "receivable"), key=lambda item: (item.due_date or "", item.case_no, item.identity))),
            sum(item.direction == "receivable" for item in undated))

    def query(self, start_month: str, end_month: str, category: str, *, today: date | None = None):
        start, end = month_start(start_month), month_start(end_month)
        if start > end or category not in {"all", "subsidy", "non_citizen"}:
            raise ValueError("invalid_accounting_range")
        today = today or datetime.now(TAIPEI_TIME_ZONE).date()
        selected, excluded, items, undated = self._items(start, end, category)
        banks, seen, cash_unavailable = [], set(), None
        for bank in self.source.bank_facts(start, end):
            if bank.identity in seen:
                raise MonthlyAccountingUnavailable("duplicate_accounting_bank_identity")
            seen.add(bank.identity)
            if date.fromisoformat(bank.occurred_on) > today:
                continue
            matching = set(bank.cases) & selected
            if not matching:
                continue
            # A bank amount is counted once. Never fabricate a per-case split.
            if set(bank.cases) - selected:
                cash_unavailable = "mixed_accounting_bank_scope"
                continue
            banks.append(bank)
        if cash_unavailable:
            banks = []
        recognitions=[];recognition_unavailable=None
        for event in self.source.recognitions(start,end):
            if date.fromisoformat(event.confirmed_on)>today or not set(event.cases)&selected:
                continue
            if set(event.cases)-selected:
                recognition_unavailable='mixed_accounting_recognition_scope'
                continue
            recognitions.append(event)
        if recognition_unavailable:
            recognitions=[]
        months, current = [], start
        while current <= end:
            key = current.strftime("%Y-%m")
            cohort = tuple(item for item in items if item.due_date[:7] == key)
            cash = tuple(bank for bank in banks if bank.occurred_on[:7] == key)
            incoming = tuple(item for item in cohort if item.direction == "receivable")
            outgoing = tuple(item for item in cohort if item.direction == "payable")
            months.append(MonthlyAccountingRow(key,
                sum(i.expected_ntd for i in incoming), sum(i.actual_ntd for i in incoming),
                sum(i.remaining_ntd for i in incoming),
                sum(i.expected_ntd for i in outgoing), sum(i.actual_ntd for i in outgoing),
                sum(i.remaining_ntd for i in outgoing),
                None if cash_unavailable else sum(b.amount_ntd for b in cash if b.direction == "in"),
                None if cash_unavailable else sum(b.amount_ntd for b in cash if b.direction == "out"), cohort, cash,
                sum(i.noncash_ntd for i in incoming), sum(i.noncash_ntd for i in outgoing),
                None if cash_unavailable or any(bank.cash_flow is None for bank in cash) else
                {flow: sum(bank.amount_ntd for bank in cash if bank.cash_flow == flow) for flow in ("C", "G", "PS", "PT", "RS", "RT")}))
            if current == end:
                break
            current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
        return MonthlyAccountingReport(start_month, end_month, category, today.isoformat(), tuple(months),
            tuple(sorted(excluded)), len(undated), cash_unavailable,tuple(recognitions),recognition_unavailable)
