"""Project an actual government refund overpayment without changing either ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection
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
        del request
        raise RuntimeError("GOVSUB-007 runtime anomaly producer is retired")


def build_government_return_outbound_overage_request(root_fact: GovernmentReturnOutboundOverageRootFact) -> ProjectAlertRequest:
    del root_fact
    raise ValueError("GOVSUB-007 runtime anomaly producer is retired")
