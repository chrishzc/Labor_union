"""Project an actual government refund overpayment without changing either ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest

_CODE = "GOVSUB-007"
_CONSUMER_IDENTITY = "government-return-outbound-overage-v1"
_MAXIMUM_SCAN_SIZE = 100


@dataclass(frozen=True, slots=True)
class GovernmentReturnOutboundOverageRootFact:
    finance_import_row_id: int
    bank_fact_identity: str
    payable_identity: str
    overpayment_identity: str
    bank_amount_ntd: int
    payable_remaining_ntd: int
    source_version: int

    def __post_init__(self) -> None:
        require_positive_integer(self.finance_import_row_id, "finance import row id")
        require_canonical_text(self.bank_fact_identity, "bank fact identity", 191)
        require_canonical_text(self.payable_identity, "return payable identity", 191)
        require_canonical_text(self.overpayment_identity, "overpayment identity", 191)
        require_positive_integer(self.bank_amount_ntd, "outgoing bank amount")
        require_positive_integer(self.payable_remaining_ntd, "return payable remaining")
        require_positive_integer(self.source_version, "return payable version")

    @property
    def excess_amount_ntd(self) -> int:
        return self.bank_amount_ntd - self.payable_remaining_ntd


@dataclass(frozen=True, slots=True)
class GovernmentReturnOutboundOverageScanRequest:
    limit: int
    after_finance_import_row_id: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        if isinstance(self.after_finance_import_row_id, bool) or self.after_finance_import_row_id < 0:
            raise ValueError("finance import scan cursor is invalid")


@dataclass(frozen=True, slots=True)
class GovernmentReturnOutboundOverageScanPage:
    facts: tuple[GovernmentReturnOutboundOverageRootFact, ...]
    next_finance_import_row_id: int | None


@dataclass(frozen=True, slots=True)
class GovernmentReturnOutboundOverageScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_finance_import_row_id: int | None


class GovernmentReturnOutboundOverageRootFactSource(Protocol):
    def load_page(self, request: GovernmentReturnOutboundOverageScanRequest) -> GovernmentReturnOutboundOverageScanPage: ...


class GovernmentReturnOutboundOverageAnomalyConsumer:
    def __init__(self, source: GovernmentReturnOutboundOverageRootFactSource, application: AnomalyApplication) -> None:
        self._source = source
        self._application = application

    def scan_page(self, request: GovernmentReturnOutboundOverageScanRequest) -> GovernmentReturnOutboundOverageScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        projections = tuple(
            self._application.project(build_government_return_outbound_overage_request(fact))
            for fact in page.facts
        )
        return GovernmentReturnOutboundOverageScanResult(projections, page.next_finance_import_row_id)


def build_government_return_outbound_overage_request(root_fact: GovernmentReturnOutboundOverageRootFact) -> ProjectAlertRequest:
    if root_fact.excess_amount_ntd <= 0:
        raise ValueError("government_return_outbound_overage_not_present")
    source_identity = f"finance-import-row:{root_fact.finance_import_row_id}:return:{root_fact.payable_identity}"
    snapshot = {
        "bank_amount_ntd": root_fact.bank_amount_ntd,
        "excess_amount_ntd": root_fact.excess_amount_ntd,
        "overpayment_identity": root_fact.overpayment_identity,
        "payable_identity": root_fact.payable_identity,
        "payable_remaining_ntd": root_fact.payable_remaining_ntd,
    }
    desired = DesiredAlertState(
        _CODE,
        source_identity,
        root_fact.source_version,
        True,
        {"payable_identity": root_fact.payable_identity},
    )
    event_identity = _event_identity(root_fact, snapshot)
    return ProjectAlertRequest(desired, event_identity, _CONSUMER_IDENTITY, source_identity, snapshot)


def _event_identity(root_fact: GovernmentReturnOutboundOverageRootFact, snapshot: dict[str, int | str]) -> str:
    digest = fingerprint_payload({"bank_fact_identity": root_fact.bank_fact_identity, "snapshot": snapshot}).value
    return f"government-return-outbound-overage:{digest}"
