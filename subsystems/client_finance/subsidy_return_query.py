"""Bounded case-based query for customer subsidy returns."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from domains.client_finance.subsidy_return_projection import project_subsidy_return
from domains.orders.lifecycle import OrderLifecycleStatus


@dataclass(frozen=True, slots=True)
class SubsidyReturnCaseFacts:
    case_no: str
    client_name: str
    order_status: str
    identity_status: str
    service_hours: Decimal | None
    floor_fee: Decimal | None
    client_hourly_rate_ntd: int | None
    actual_end_date: date | None
    has_formal_return: bool
    formal_amount_ntd: int | None
    formal_due_date: date | None
    return_settled: bool


@dataclass(frozen=True, slots=True)
class SubsidyReturnRow:
    case_no: str
    client_name: str
    order_status: str
    amount_ntd: int | None
    due_date: date | None
    is_estimate: bool


@dataclass(frozen=True, slots=True)
class SubsidyReturnPage:
    rows: tuple[SubsidyReturnRow, ...]
    next_cursor: str | None


class SubsidyReturnQueryRepository(Protocol):
    def query_facts(self, *, after_case_no: str | None, case_no: str | None,
                    search: str | None, limit: int) -> tuple[SubsidyReturnCaseFacts, ...]: ...


_COMPLETED = {
    OrderLifecycleStatus.COMPLETED, OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
    OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
}


def query_subsidy_returns(repository: SubsidyReturnQueryRepository, *, page_size: int = 100,
                         after_case_no: str | None = None, case_no: str | None = None,
                         search: str | None = None, target_month: str | None = None) -> SubsidyReturnPage:
    facts = repository.query_facts(after_case_no=after_case_no, case_no=case_no,
                                   search=search, limit=page_size + 1)
    rows = []
    for fact in facts[:page_size]:
        if fact.order_status == OrderLifecycleStatus.CANCELLED:
            continue
        projection = project_subsidy_return(
            identity_status=fact.identity_status, service_hours=fact.service_hours,
            floor_fee=fact.floor_fee, client_hourly_rate_ntd=fact.client_hourly_rate_ntd,
            completed_on=fact.actual_end_date if fact.order_status in _COMPLETED else None,
            has_formal_return=fact.has_formal_return, formal_amount_ntd=fact.formal_amount_ntd,
            formal_due_date=fact.formal_due_date, return_settled=fact.return_settled,
        )
        if projection is None:
            continue
        if target_month and (projection.due_date is None or projection.due_date.strftime('%Y-%m') != target_month):
            continue
        rows.append(SubsidyReturnRow(fact.case_no, fact.client_name, fact.order_status,
                                    projection.amount_ntd, projection.due_date, projection.is_estimate))
    return SubsidyReturnPage(tuple(rows), facts[page_size - 1].case_no if len(facts) > page_size else None)
