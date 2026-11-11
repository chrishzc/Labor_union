"""Compose typed owner queries; display warnings never change accounting facts."""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Protocol
from domains.client_finance.obligation_planning import ClientSubsidyReturnPlan
from domains.payroll.installments import PayrollInstallment
from shared_kernel.fingerprints import PreviewFingerprint

from domains.finance_import.statement_archive import (
    accounting_warning, case_accounting_scheme, direct_arrangement_conflict,
    direct_arrangement_ready, ArrangementEvent, CaseArrangement,
    CaseSubsidyPlan, ongoing_case_completed,
)
from domains.finance_import.statement_archive import CollectionProgress, CollectionStageSource, current_collection_progress
from subsystems.client_finance.case_accounting_query import (
    ClientAccountingItem, ClientAccountingTransaction, ClientCancellationAccounting, ClientCaseFunding, ClientCasePaymentTerms,
)
from subsystems.staff_payables.case_accounting_query import StaffAccountingItem, StaffAccountingTransaction


@dataclass(frozen=True)
class SubsidyPlanApplyResult:
    case_no: str
    applied_version: int
    plan: CaseSubsidyPlan


@dataclass(frozen=True)
class SubsidyPlanPayable:
    identity: str
    recipient: str
    amount_ntd: int
    due_date: str | None


@dataclass(frozen=True)
class SubsidyPlanPreview:
    case_no: str
    scheme: str
    plan_version: int
    subsidy_ntd: int | None
    total_ntd: int | None
    confirmation_only: bool
    payables: tuple[SubsidyPlanPayable, ...]
    blocker: str | None
    fingerprint: PreviewFingerprint
    refund_plan: ClientSubsidyReturnPlan | None = None
    staff_identity: str | None = None
    installments: tuple[PayrollInstallment, ...] = ()


class AccountingConflict(ValueError):
    pass


class ArrangementNotReady(ValueError):
    pass


@dataclass(frozen=True)
class ArrangementApplyResult:
    case_no: str
    applied_version: int
    arrangement: CaseArrangement


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
class AccountingBankFact:
    identity: str
    occurred_on: str
    direction: str
    amount_ntd: int
    cases: tuple[str, ...]
    bank: str | None = None
    cash_flow: str | None = None


@dataclass(frozen=True)
class CaseBankMemo:
    identity: str
    occurred_on: str | None
    memo: str


@dataclass(frozen=True)
class SubsidyPayment:
    recipient: str
    party: str
    amount_ntd: int
    due_date: str | None
    source: str


def _subsidy_payments(scheme, subsidy, service_end, client_name, client_items, staff_items):
    from domains.client_finance.subsidy_advance import subsidy_advance_due_date

    formal = (
        *(SubsidyPayment("staff", item.party, portion.amount_ntd,
                         portion.due_date.isoformat() if portion.due_date else None, "formal")
          for item in staff_items for portion in item.funding_portions if portion.funding_kind == "subsidy"),
        *(SubsidyPayment("client", item.party, item.expected_ntd, item.due_date, "formal")
          for item in client_items if item.obligation_type == "subsidy_return" and item.direction == "payable"),
    )
    if formal:
        return formal
    if scheme not in {"split", "advance"} or subsidy is None or subsidy <= 0:
        return ()
    date = subsidy_advance_due_date(service_end).isoformat() if service_end else None
    if scheme == "advance":
        return (SubsidyPayment("client", client_name, subsidy, date, "estimate"),)
    staff = "、".join(dict.fromkeys(item.party for item in staff_items if item.party))
    return (SubsidyPayment("staff", staff, subsidy, date, "estimate"),)


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
    bank_facts: tuple[AccountingBankFact, ...] = ()
    historical_marker: HistoricalAccountingMarker | None = None
    remaining_in_ntd: int | None = None
    remaining_out_ntd: int | None = None
    staff_receivable_ntd: int | None = None
    customer_amount_ntd: int | None = None
    customer_fully_received: bool | None = None
    subsidy_ntd: int | None = None
    scheme: str = "unknown"
    cash_by_flow: dict[str, int] | None = None
    cash_net_ntd: int | None = None
    customer_burden_ntd: int | None = None
    arrangement: CaseArrangement | None = None
    scheme_conflict: bool = False
    can_confirm_direct: bool = False
    collection_progress: CollectionProgress | None = None
    subsidy_plan: CaseSubsidyPlan | None = None
    ongoing_completed: bool = False
    customer_paid_ntd: int | None = None
    funding: ClientCaseFunding | None = None
    cancellation_settlement: ClientCancellationAccounting | None = None
    bank_memos: tuple[CaseBankMemo, ...] = ()
    subsidy_payments: tuple[SubsidyPayment, ...] = ()


@dataclass(frozen=True)
class HistoricalAccountingAmount:
    identity: str
    direction: str
    expected_ntd: int
    actual_ntd: int
    remaining_ntd: int


@dataclass(frozen=True)
class HistoricalAccountingMarker:
    case_no: str
    reason: str
    actor: str
    created_at: str
    amounts: tuple[HistoricalAccountingAmount, ...] = ()


class AccountingStatePort(Protocol):
    def case_client(self, case_no: str) -> str: ...
    def arrangement(self, case_no: str) -> CaseArrangement: ...
    def subsidy_plan(self, case_no: str) -> CaseSubsidyPlan: ...
    def subsidy_plan_command(self, key: str) -> tuple[str, int, str, str] | None: ...
    def append_subsidy_plan(self, case_no: str, version: int, scheme: str, actor: str, key: str) -> None: ...
    def lock_arrangement_case(self, case_no: str) -> None: ...
    def arrangement_command(self, key: str) -> tuple[str, int, str, str, str] | None: ...
    def append_arrangement(self, case_no: str, version: int, action: str, reason: str, actor: str, key: str) -> None: ...
    def dismissed(self, case_no: str, *, for_update=False): ...
    def dismiss(self, case_no, warning, actor): ...
    def begin(self): ...
    def commit(self): ...
    def rollback(self): ...
    def payment_cases(self) -> tuple[str, ...]: ...
    def marker(self, case_no: str) -> HistoricalAccountingMarker | None: ...
    def marker_command(self, key: str): ...
    def mark(self, case_no: str, reason: str, actor: str, versions: dict[str, str], key: str, amounts: tuple[HistoricalAccountingAmount, ...]): ...


class ClientAccountingPort(Protocol):
    def __call__(self, case_no: str, *, for_update=False) -> tuple[tuple[ClientAccountingItem, ...], tuple[ClientAccountingTransaction, ...]]: ...


class StaffAccountingPort(Protocol):
    def __call__(self, case_no: str, *, for_update=False) -> tuple[tuple[StaffAccountingItem, ...], tuple[StaffAccountingTransaction, ...]]: ...


class AccountingWorkspace:
    def __init__(self, state: AccountingStatePort, client: ClientAccountingPort, staff: StaffAccountingPort,
                 bank=None, subsidy=None, payment_terms=None, plan=None, cancellation=None, bank_memos=None,
                 subsidy_plan_preview=None, subsidy_plan_apply=None):
        self.state, self.client, self.staff = state, client, staff
        self.bank = bank
        self.subsidy = subsidy
        self.payment_terms = payment_terms
        self.plan = plan
        self.cancellation = cancellation
        self.bank_memos = bank_memos
        self.subsidy_plan_preview = subsidy_plan_preview
        self.subsidy_plan_apply = subsidy_plan_apply

    def subsidy_plan_history(self, case_no: str):
        self.state.case_client(case_no)
        return self.state.subsidy_plan(case_no)

    def preview_subsidy_plan(self, case_no: str, scheme: str, expected_version: int):
        self.state.case_client(case_no)
        if scheme not in {'split','advance','direct'} or expected_version < 0:
            raise ValueError('subsidy_plan_command_invalid')
        if self.state.subsidy_plan(case_no).version != expected_version:
            raise AccountingConflict('subsidy_plan_version_changed')
        return self.subsidy_plan_preview(case_no, scheme, expected_version, for_update=False)

    def save_subsidy_plan(self, case_no: str, scheme: str, expected_version: int, key: str, actor: str,
                          preview_fingerprint: str | None = None):
        if scheme not in {"split", "advance", "direct"} or expected_version < 0 or not key.strip() or not actor.strip() or key.startswith('bank-subsidy:'):
            raise ValueError("subsidy_plan_command_invalid")
        command = (case_no, expected_version, scheme, actor)
        self.state.begin()
        try:
            self.state.lock_arrangement_case(case_no)
            previous = self.state.subsidy_plan_command(key)
            if previous is not None:
                if previous != command:
                    raise AccountingConflict("subsidy_plan_command_changed")
                result = SubsidyPlanApplyResult(case_no, expected_version + 1, self.state.subsidy_plan(case_no))
            else:
                current = self.state.subsidy_plan(case_no)
                if current.version != expected_version:
                    raise AccountingConflict("subsidy_plan_version_changed")
                preview = self.subsidy_plan_preview(case_no, scheme, expected_version, for_update=True) if self.subsidy_plan_preview else None
                if preview is not None:
                    if ((preview.payables or preview.blocker or preview_fingerprint is not None)
                            and preview_fingerprint != preview.fingerprint.value):
                        raise AccountingConflict('subsidy_plan_preview_changed')
                self.state.append_subsidy_plan(case_no, expected_version + 1, scheme, actor, key)
                if preview is not None and self.subsidy_plan_apply is not None:
                    self.subsidy_plan_apply(preview, actor, key)
                result = SubsidyPlanApplyResult(case_no, expected_version + 1, self.state.subsidy_plan(case_no))
            self.state.commit()
            return result
        except Exception:
            self.state.rollback()
            raise

    def arrangement_history(self, case_no: str):
        self.state.case_client(case_no)
        return self.state.arrangement(case_no)

    def confirm_arrangement(self, case_no: str, action: str, reason: str, expected_version: int, key: str, actor: str):
        reason = reason.strip()
        if action not in {"confirm_direct", "withdraw_direct"} or not reason or len(reason) > 500 or not key.strip() or expected_version < 0:
            raise ArrangementNotReady("arrangement_command_invalid")
        command = (case_no, expected_version, action, reason, actor)
        self.state.begin()
        try:
            self.state.lock_arrangement_case(case_no)
            previous = self.state.arrangement_command(key)
            if previous:
                if previous != command:
                    raise AccountingConflict("arrangement_command_changed")
                history = self.state.arrangement(case_no)
                self.state.commit()
                return ArrangementApplyResult(case_no, expected_version + 1, history)
            current = self.state.arrangement(case_no)
            if current.version != expected_version:
                raise AccountingConflict("arrangement_version_changed")
            if action == "confirm_direct":
                fresh = self.query(case_no, for_update=True)
                if not fresh.can_confirm_direct:
                    raise ArrangementNotReady("direct_arrangement_not_ready")
            elif not current.direct_confirmed:
                raise ArrangementNotReady("direct_arrangement_not_confirmed")
            self.state.append_arrangement(case_no, expected_version + 1, action, reason, actor, key)
            history = self.state.arrangement(case_no)
            self.state.commit()
            return ArrangementApplyResult(case_no, expected_version + 1, history)
        except Exception:
            self.state.rollback()
            raise

    def mark_historical(self, case_no: str, reason: str, versions: dict[str, str], key: str, actor: str):
        if not reason.strip() or not key.strip():
            raise ValueError("historical_accounting_reason_required")
        self.state.begin()
        try:
            previous = self.state.marker_command(key)
            if previous:
                if previous != (case_no, reason, actor, versions):
                    raise AccountingConflict("historical_accounting_command_changed")
                self.state.commit()
                return self.state.marker(case_no)
            current = self.query(case_no, for_update=True, include_sources=False)
            if self.state.marker(case_no):
                if self.state.marker_command(key) == (case_no, reason, actor, versions):
                    self.state.commit()
                    return self.state.marker(case_no)
                raise AccountingConflict("historical_accounting_already_marked")
            fresh = {item.identity: item.version for item in (*current.client_items, *current.staff_items)}
            if fresh != versions:
                raise AccountingConflict("historical_accounting_source_changed")
            amounts = tuple(HistoricalAccountingAmount(item.identity, item.direction, item.expected_ntd, item.actual_ntd, item.remaining_ntd)
                            for item in (*current.client_items, *current.staff_items) if getattr(item, "summary_included", True))
            self.state.mark(case_no, reason, actor, versions, key, amounts)
            self.state.commit()
            return self.state.marker(case_no)
        except Exception:
            self.state.rollback()
            raise

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

    def query(self, case_no, *, for_update=False, include_sources=True):
        client_name = self.state.case_client(case_no)
        client_items, client_transactions = self.client(case_no, for_update=for_update)
        staff_items, staff_transactions = self.staff(case_no, for_update=for_update)
        dismissals = self.state.dismissed(case_no, for_update=for_update)
        warnings = []
        items = (*client_items, *staff_items)
        for item in items:
            if item.settled and item.actual_ntd<=item.expected_ntd:
                continue
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
        banks = self.bank(case_no) if include_sources and self.bank is not None else ()
        stages = [item for item in client_items if item.payment_stage in {"deposit", "first", "second"}]
        terms = self.payment_terms(case_no) if include_sources and self.payment_terms is not None else ClientCasePaymentTerms()
        recorded_stages = {item.payment_stage for item in stages}
        collection_sources = (
            *(CollectionStageSource(item.payment_stage, item.expected_ntd, item.actual_ntd, item.due_date) for item in stages),
            *(CollectionStageSource(stage.value, 0, 0, None) for stage in terms.zero_stages if stage not in recorded_stages),
        )
        complete_terms = bool(stages) if terms.historical_stages else (
            len(collection_sources) == 3 and {item.stage for item in collection_sources} == {"deposit", "first", "second"})
        customer_amount = sum(item.expected_ntd for item in collection_sources) if complete_terms else None
        customer_paid = sum(item.received_ntd for item in collection_sources) if complete_terms else None
        fully_received = all(item.received_ntd >= item.expected_ntd for item in collection_sources) if complete_terms else None
        staff_due = [item for item in staff_items if item.direction == "payable" and item.summary_included]
        staff_total = sum(item.expected_ntd for item in staff_due) if staff_due else None
        subsidy = self.subsidy(case_no) if include_sources and self.subsidy is not None else None
        funding = terms.funding
        full_subsidy = bool(funding and funding.full_subsidy)
        funding_conflict = False
        if full_subsidy:
            funding_conflict = (funding.has_subsidy_return or any(item.expected_ntd or item.actual_ntd or item.noncash_ntd for item in stages)
                or (staff_total is not None and staff_total != funding.total_ntd)
                or (subsidy is not None and subsidy != funding.total_ntd))
            if not funding_conflict:
                staff_total, customer_amount, subsidy, fully_received = funding.total_ntd, 0, funding.total_ntd, True
                customer_paid = 0
        government = sum(bank.amount_ntd for bank in banks if bank.cash_flow == "G" and bank.cases == (case_no,))
        cash_flows = None
        if include_sources and self.bank is not None and all(bank.cash_flow in {"C", "G", "PS", "PT", "RS", "RT"} and bank.cases == (case_no,) for bank in banks):
            cash_flows = {flow: sum(bank.amount_ntd for bank in banks if bank.cash_flow == flow) for flow in ("C", "G", "PS", "PT", "RS", "RT")}
        cash_net = None if cash_flows is None else cash_flows["C"] + cash_flows["G"] - sum(cash_flows[flow] for flow in ("PS", "PT", "RS", "RT"))
        arrangement = self.state.arrangement(case_no) if include_sources and self.bank is not None else None
        direct = bool(arrangement and arrangement.direct_confirmed)
        conflict = funding_conflict or (direct and direct_arrangement_conflict(staff_total, customer_amount, government,
            sum(bank.amount_ntd for bank in banks if bank.cash_flow == "PT" and bank.cases == (case_no,)),
            sum(bank.amount_ntd for bank in banks if bank.cash_flow == "RT" and bank.cases == (case_no,))))
        scheme = case_accounting_scheme(staff_total, customer_amount, subsidy, fully_received, government,
            direct_confirmed=direct, bank_sources_complete=cash_flows is not None, direct_conflict=conflict,
            full_subsidy=full_subsidy)
        plan = self.plan(case_no) if include_sources and self.plan is not None else None
        if plan is not None and plan.selected_scheme is not None:
            scheme = plan.selected_scheme
        return CaseAccounting(
            case_no, client_name,
            sum(item.expected_ntd for item in incoming) if incoming else None,
            sum(item.actual_ntd for item in incoming) if incoming else None,
            sum(item.expected_ntd for item in outgoing) if outgoing else None,
            sum(item.actual_ntd for item in outgoing) + unallocated if outgoing else None,
            sum(not warning.dismissed for warning in warnings), client_items, staff_items,
            (*client_transactions, *staff_transactions), tuple(warnings),
            banks,
            self.state.marker(case_no) if include_sources and self.bank is not None else None,
            sum(item.remaining_ntd for item in incoming) if incoming else None,
            sum(item.remaining_ntd for item in outgoing) if outgoing else None,
            staff_total, customer_amount, fully_received, subsidy, scheme, cash_flows, cash_net,
            staff_total - subsidy if staff_total is not None and subsidy is not None else None,
            arrangement, conflict, direct_arrangement_ready(staff_total, customer_amount, subsidy, fully_received, cash_flows),
            CollectionProgress("scheme", True) if full_subsidy and not funding_conflict else current_collection_progress(collection_sources, historical=terms.historical_stages),
            plan, ongoing_case_completed(fully_received, plan),
            customer_paid_ntd=customer_paid, funding=funding,
            cancellation_settlement=self.cancellation(case_no) if include_sources and self.cancellation else None,
            bank_memos=self.bank_memos(case_no) if include_sources and self.bank_memos else (),
            subsidy_payments=_subsidy_payments(
                scheme, subsidy, terms.service_end_date, client_name, client_items, staff_due,
            ) if include_sources else (),
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
