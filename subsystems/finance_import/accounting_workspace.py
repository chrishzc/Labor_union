"""Compose typed owner queries; display warnings never change accounting facts."""
from dataclasses import dataclass, replace
from typing import Protocol

from domains.finance_import.statement_archive import accounting_warning
from subsystems.client_finance.case_accounting_query import ClientAccountingItem, ClientAccountingTransaction
from subsystems.staff_payables.case_accounting_query import StaffAccountingItem, StaffAccountingTransaction


class AccountingConflict(ValueError):
    pass


@dataclass(frozen=True)
class AccountingWarning:
    item_identity: str
    kind: str
    expected_ntd: int
    actual_ntd: int
    difference_ntd: int
    source_version: str
    dismissed: bool = False
    dismissed_by: str | None = None
    dismissed_at: str | None = None


@dataclass(frozen=True)
class CaseAccounting:
    case_no: str
    client_name: str
    receivable_ntd: int | None
    received_ntd: int | None
    payable_ntd: int | None
    paid_ntd: int | None
    pending_warning_count: int
    client_items: tuple[ClientAccountingItem, ...]
    staff_items: tuple[StaffAccountingItem, ...]
    transactions: tuple[ClientAccountingTransaction | StaffAccountingTransaction, ...]
    warnings: tuple[AccountingWarning, ...]


class AccountingStatePort(Protocol):
    def case_client(self, case_no: str) -> str: ...
    def dismissed(self, case_no: str, *, for_update=False): ...
    def dismiss(self, case_no, warning, actor): ...
    def begin(self): ...
    def commit(self): ...
    def rollback(self): ...
    def payment_cases(self) -> tuple[str, ...]: ...


class ClientAccountingPort(Protocol):
    def __call__(self, case_no: str, *, for_update=False) -> tuple[tuple[ClientAccountingItem, ...], tuple[ClientAccountingTransaction, ...]]: ...


class StaffAccountingPort(Protocol):
    def __call__(self, case_no: str, *, for_update=False) -> tuple[tuple[StaffAccountingItem, ...], tuple[StaffAccountingTransaction, ...]]: ...


class AccountingWorkspace:
    def __init__(self, state: AccountingStatePort, client: ClientAccountingPort, staff: StaffAccountingPort):
        self.state, self.client, self.staff = state, client, staff

    def warnings(self):
        cases, seen = [], set()
        for case_no in self.state.payment_cases():
            case = self.query(case_no)
            warnings = []
            for warning in case.warnings:
                key = (warning.item_identity, warning.kind, warning.difference_ntd)
                if key not in seen:
                    seen.add(key)
                    warnings.append(warning)
            if warnings:
                cases.append(replace(case, warnings=tuple(warnings), pending_warning_count=sum(not row.dismissed for row in warnings)))
        return tuple(cases)

    def query(self, case_no, *, for_update=False):
        client_name = self.state.case_client(case_no)
        client_items, client_transactions = self.client(case_no, for_update=for_update)
        staff_items, staff_transactions = self.staff(case_no, for_update=for_update)
        dismissals = self.state.dismissed(case_no, for_update=for_update)
        warnings = []
        items = (*client_items, *staff_items)
        for item in items:
            kind = accounting_warning(item.direction, item.expected_ntd, item.actual_ntd, item.has_payment)
            if kind is None:
                continue
            warning = AccountingWarning(item.identity, kind, item.expected_ntd, item.actual_ntd,
                                        item.expected_ntd - item.actual_ntd, item.version)
            previous = dismissals.get((item.identity, kind, warning.difference_ntd))
            if previous:
                warning = replace(warning, dismissed=True, dismissed_by=previous[0], dismissed_at=previous[1])
            warnings.append(warning)
        incoming = [item for item in items if item.direction == "receivable" and getattr(item, "summary_included", True)]
        outgoing = [item for item in items if item.direction == "payable" and getattr(item, "summary_included", True)]
        unallocated = sum(item.unallocated_surplus_ntd for item in staff_items)
        return CaseAccounting(
            case_no, client_name,
            sum(item.expected_ntd for item in incoming) if incoming else None,
            sum(item.actual_ntd for item in incoming) if incoming else None,
            sum(item.expected_ntd for item in outgoing) if outgoing else None,
            sum(item.actual_ntd for item in outgoing) + unallocated if outgoing else None,
            sum(not warning.dismissed for warning in warnings), client_items, staff_items,
            (*client_transactions, *staff_transactions), tuple(warnings),
        )

    def dismiss(self, case_no, target: AccountingWarning, actor):
        self.state.begin()
        try:
            fresh = self.query(case_no, for_update=True)
            current = next((row for row in fresh.warnings if row.item_identity == target.item_identity and row.kind == target.kind), None)
            if current is None or (
                current.source_version, current.expected_ntd, current.actual_ntd, current.difference_ntd
            ) != (target.source_version, target.expected_ntd, target.actual_ntd, target.difference_ntd):
                raise AccountingConflict("accounting_warning_changed")
            if not current.dismissed:
                self.state.dismiss(case_no, current, actor)
            self.state.commit()
            return self.query(case_no)
        except Exception:
            self.state.rollback()
            raise
