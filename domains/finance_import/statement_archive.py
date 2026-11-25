"""Statement columns, warnings and explicit case-arrangement policy."""
from __future__ import annotations

from dataclasses import dataclass

STATEMENT_COLUMNS = (
    "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出", "存入", "餘額",
    "票據號碼", "銷帳編號", "交易參考編號", "備註", "更正註記", "存摺備註",
)


def accounting_warning(direction: str, expected: int, actual: int, has_payment: bool) -> str | None:
    """No tolerance, allocation or settlement rules are changed here."""
    difference = expected - actual
    if direction == "receivable" and difference < 0:
        return "over_received"
    if direction == "payable" and difference < 0:
        return "over_paid"
    if direction == "payable" and has_payment and difference > 100:
        return "under_paid"
    return None


def bank_import_type(format_id: str, direction: str) -> str:
    if format_id == "sinopac":
        return {"incoming": "receivable", "outgoing": "payable"}.get(direction, "review")
    if format_id == "taishin":
        return {"incoming": "government_subsidy", "outgoing": "subsidy_return"}.get(direction, "review")
    return "legacy"


@dataclass(frozen=True)
class ReconciledSubsidyEvidence:
    receipts: tuple[tuple[str, int], ...] = ()
    staff_payouts: tuple[str, ...] = ()
    customer_refunds: tuple[str, ...] = ()
    government_received: bool = False
    ambiguous: bool = False

    @property
    def customer_received(self) -> int:
        return sum(amount for _, amount in self.receipts)


@dataclass(frozen=True)
class SubsidySchemeDecision:
    scheme: str = "unknown"
    source: str | None = None
    evidence_identities: tuple[str, ...] = ()
    pending_reason: str | None = None


def case_accounting_scheme(
    total: int | None, subsidy: int | None, evidence: ReconciledSubsidyEvidence,
) -> SubsidySchemeDecision:
    received = evidence.customer_received
    reason = None
    if evidence.ambiguous:
        reason = "subsidy_evidence_ambiguous"
    elif evidence.staff_payouts and evidence.customer_refunds:
        reason = "subsidy_payout_conflict"
    elif total is None:
        reason = "subsidy_case_total_unknown"
    elif subsidy is None:
        reason = "subsidy_amount_unknown"
    elif not 0 < subsidy <= total:
        reason = "subsidy_amount_invalid"
    elif received > total:
        reason = "subsidy_receipt_over_total"
    elif received <= 0:
        reason = "subsidy_receipt_missing"
    elif received == total:
        receipts = tuple(identity for identity, _ in evidence.receipts)
        if evidence.staff_payouts:
            return SubsidySchemeDecision("split", "bank", (*receipts, *evidence.staff_payouts))
        if evidence.customer_refunds:
            return SubsidySchemeDecision("advance", "bank", (*receipts, *evidence.customer_refunds))
        reason = "subsidy_payout_missing"
    elif total - received == subsidy:
        if evidence.customer_refunds:
            reason = "subsidy_payout_conflict"
        else:
            return SubsidySchemeDecision("split", "receipt", tuple(identity for identity, _ in evidence.receipts))
    else:
        reason = "subsidy_receipt_difference_mismatch"
    return SubsidySchemeDecision(pending_reason=reason)


def direct_arrangement_ready(
    total: int | None, subsidy: int | None, evidence: ReconciledSubsidyEvidence,
) -> bool:
    return (total is not None and total > 0 and evidence.customer_received == total
            and subsidy is not None and 0 < subsidy <= total and not evidence.ambiguous
            and not evidence.government_received and not evidence.staff_payouts and not evidence.customer_refunds)


@dataclass(frozen=True)
class ArrangementEvent:
    version: int
    action: str
    reason: str
    actor: str
    created_at: str


@dataclass(frozen=True)
class CaseArrangement:
    case_no: str
    version: int = 0
    events: tuple[ArrangementEvent, ...] = ()

    @property
    def direct_confirmed(self):
        return bool(self.events and self.events[-1].action == "confirm_direct")


@dataclass(frozen=True)
class CollectionStageSource:
    stage: str
    expected_ntd: int
    received_ntd: int
    due_date: str | None


@dataclass(frozen=True)
class CollectionProgress:
    stage: str
    sources_complete: bool
    expected_ntd: int | None = None
    received_ntd: int | None = None
    remaining_ntd: int | None = None
    due_date: str | None = None


def current_collection_progress(sources: tuple[CollectionStageSource, ...], *, historical: bool = False) -> CollectionProgress:
    """Expose one current collection item; never treat missing terms as zero."""
    for stage in ("deposit", "first", "second"):
        matches = [source for source in sources if source.stage == stage]
        if historical and sources and not matches:
            continue
        if len(matches) != 1:
            return CollectionProgress(stage, False)
        source = matches[0]
        if source.expected_ntd < 0 or source.received_ntd < 0:
            return CollectionProgress(stage, False)
        if source.received_ntd < source.expected_ntd:
            return CollectionProgress(stage, True, source.expected_ntd, source.received_ntd,
                                      source.expected_ntd - source.received_ntd, source.due_date)
    return CollectionProgress("scheme", True)


@dataclass(frozen=True)
class SubsidyPlanEvent:
    version: int
    scheme: str
    actor: str
    created_at: str
    source: str = "manual"
    bank_row_identity: str | None = None
    receipt_identity: str | None = None

    @property
    def evidence_identity(self) -> str | None:
        if self.source == "receipt":
            return self.receipt_identity
        if self.source == "bank" and self.bank_row_identity:
            return self.bank_row_identity.replace("finance-import-row:", "bank:", 1)
        return None


@dataclass(frozen=True)
class CaseSubsidyPlan:
    case_no: str
    version: int = 0
    events: tuple[SubsidyPlanEvent, ...] = ()

    @property
    def selected_scheme(self) -> str | None:
        return self.events[-1].scheme if self.events else None

    @property
    def confirmation_source(self) -> str | None:
        return self.events[-1].source if self.events else None


def ongoing_case_completed(fully_received: bool | None, plan: CaseSubsidyPlan | None) -> bool:
    return fully_received is True and plan is not None and plan.selected_scheme in {"split", "advance", "direct"}
