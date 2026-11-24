"""Orders rules and observations for a staff-confirmed historical correction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from domains.client_finance.obligation_planning import PriorClientCancellationBalance
from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleStatus
from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class HistoricalUnservedCorrectionIntent:
    reason: str = ""
    evidence_source: str = ""
    confirmed_actual_service_day_count: Literal[0] = 0

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "historical correction reason", 500, allow_empty=True)
        require_canonical_text(self.evidence_source, "historical correction evidence source", 191, allow_empty=True)
        if type(self.confirmed_actual_service_day_count) is not int or self.confirmed_actual_service_day_count != 0:
            raise ValueError("historical_unserved_confirmation_required")

    @property
    def resulting_status(self) -> OrderLifecycleStatus:
        return OrderLifecycleStatus.ESTABLISHED_UNSERVED


@dataclass(frozen=True, slots=True)
class HistoricalCancellationSettlement:
    cancellation_event_id: int
    cancellation_control_event_id: int
    official_service_day_count: int
    finance_receipt_id: int | None
    fee_ntd: int = 0
    fee_reason: str = ""
    service_due_ntd: int = 0
    obligation_identity: str | None = None
    client_balance: PriorClientCancellationBalance | None = None


@dataclass(frozen=True, slots=True)
class HistoricalUnservedEvidence:
    establishment: OrderEstablishmentEvidence
    historical_adoption_ids: tuple[int, ...]
    historical_absence_event_ids: tuple[int, ...]
    actual_service_evidence: tuple[str, ...]
    prior_settlement: HistoricalCancellationSettlement | None
    blockers: tuple[str, ...] = ()
    actual_end_date: date | None = None
    standalone_assignment_ids: tuple[int, ...] = ()
    standalone_staff_ids: tuple[int, ...] = ()
    review_codes: tuple[str, ...] = ()


_CORRECTABLE_STATUSES = frozenset({
    OrderLifecycleStatus.CANCELLED,
    OrderLifecycleStatus.HISTORICAL_UNSERVED,
    OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
    OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
})


def is_historical_unserved_correctable(current_status: OrderLifecycleStatus) -> bool:
    return current_status in _CORRECTABLE_STATUSES


def historical_unserved_blockers(
    evidence: HistoricalUnservedEvidence | None,
    current_status: OrderLifecycleStatus,
) -> tuple[str, ...]:
    if not is_historical_unserved_correctable(current_status):
        return ("historical_unserved_status_ineligible",)
    return evidence.blockers if evidence else ()


def historical_unserved_review_codes(evidence: HistoricalUnservedEvidence) -> tuple[str, ...]:
    review_codes = list(evidence.review_codes)
    if not (evidence.historical_adoption_ids or evidence.historical_absence_event_ids):
        review_codes.append("historical_unserved_not_historical")
    if not evidence.establishment.established:
        review_codes.append("historical_unserved_establishment_evidence_missing")
    if evidence.actual_service_evidence or (
        evidence.prior_settlement is not None
        and evidence.prior_settlement.official_service_day_count > 0
    ):
        review_codes.append("historical_unserved_actual_service_evidence")
    return tuple(review_codes)
