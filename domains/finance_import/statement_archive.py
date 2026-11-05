"""Manual bank archive, warnings and explicit case-arrangement policy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

STATEMENT_COLUMNS = (
    "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出", "存入", "餘額",
    "票據號碼", "銷帳編號", "交易參考編號", "備註", "更正註記", "存摺備註",
)


def validate_manual_statement(fields: dict[str, str | int | None]) -> dict[str, str | int | None]:
    if set(fields) - set(STATEMENT_COLUMNS):
        raise ValueError("unknown_statement_column")
    values = {column: fields.get(column) for column in STATEMENT_COLUMNS}
    try:
        date.fromisoformat(str(values["交易日"]))
    except (ValueError, TypeError):
        raise ValueError("invalid_transaction_date") from None
    amounts = []
    for column in ("支出", "存入"):
        value = values[column]
        if value is None or value == "":
            amounts.append(0)
            continue
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValueError("invalid_statement_amount") from None
        values[column] = int(amount)
        amounts.append(int(amount))
    if sum(value > 0 for value in amounts) != 1:
        raise ValueError("one_statement_direction_required")
    if not any(str(values[column] or "").strip() for column in ("銷帳編號", "備註")):
        raise ValueError("statement_reference_required")
    return values


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


def direct_arrangement_ready(total, customer_amount, subsidy, fully_received, cash_flows):
    return (fully_received is True and total is not None and customer_amount == total
            and subsidy is not None and subsidy > 0 and cash_flows is not None
            and all(cash_flows[flow] == 0 for flow in ("G", "PT", "RT")))


def direct_arrangement_conflict(total, customer_amount, government_received, staff_subsidy_paid, client_subsidy_returned):
    return ((total is not None and customer_amount is not None and total != customer_amount)
            or any(amount > 0 for amount in (government_received, staff_subsidy_paid, client_subsidy_returned)))


def case_accounting_scheme(total, customer_amount, subsidy, fully_received, government_received, *,
                           direct_confirmed=False, bank_sources_complete=True, direct_conflict=False,
                           full_subsidy=False):
    """Classify only uniquely supported cash arrangements; no identity routing."""
    if full_subsidy:
        return "split" if total is not None and total > 0 and subsidy == total and customer_amount == 0 and not direct_confirmed and not direct_conflict else "unknown"
    if fully_received is False:
        return "waiting"
    if fully_received is not True or any(value is None for value in (total, customer_amount, subsidy)) or subsidy <= 0:
        return "unknown"
    if direct_confirmed:
        return "direct" if customer_amount == total and bank_sources_complete and not direct_conflict and government_received == 0 else "unknown"
    if customer_amount == total - subsidy:
        return "split"
    if customer_amount == total and government_received > 0:
        return "advance"
    # Absence of government cash never proves a direct-to-customer arrangement.
    return "unknown"


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


def current_collection_progress(sources: tuple[CollectionStageSource, ...]) -> CollectionProgress:
    """Expose one current collection item; never treat missing terms as zero."""
    for stage in ("deposit", "first", "second"):
        matches = [source for source in sources if source.stage == stage]
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


@dataclass(frozen=True)
class CaseSubsidyPlan:
    case_no: str
    version: int = 0
    events: tuple[SubsidyPlanEvent, ...] = ()

    @property
    def selected_scheme(self) -> str | None:
        return self.events[-1].scheme if self.events else None


def ongoing_case_completed(fully_received: bool | None, plan: CaseSubsidyPlan | None) -> bool:
    return fully_received is True and plan is not None and plan.selected_scheme in {"split", "advance", "direct"}
