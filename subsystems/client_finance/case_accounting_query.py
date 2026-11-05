"""Bounded Client Finance accounting facts for the finance workspace."""
from dataclasses import dataclass
from decimal import Decimal

from domains.client_finance.reconciliation import PaymentStage
from domains.client_finance.subsidy_coverage import is_full_subsidy_case


@dataclass(frozen=True)
class ClientCaseFunding:
    case_no: str
    identity_status: str
    service_hours: Decimal
    subsidy_limit: Decimal
    total_ntd: int
    has_subsidy_return: bool = False

    @property
    def full_subsidy(self) -> bool:
        return is_full_subsidy_case(self.identity_status, self.service_hours, self.subsidy_limit) is True


@dataclass(frozen=True)
class ClientCasePaymentTerms:
    funding: ClientCaseFunding | None = None
    zero_stages: frozenset[PaymentStage] = frozenset()


@dataclass(frozen=True)
class ClientAccountingItem:
    identity: str
    direction: str
    label: str
    party: str
    expected_ntd: int
    actual_ntd: int
    has_payment: bool
    version: str
    due_date: str | None
    settled: bool = False
    recognized_ntd: int = 0
    payment_stage: str | None = None

    @property
    def remaining_ntd(self):
        return 0 if self.settled else max(0, self.expected_ntd - self.actual_ntd - self.recognized_ntd)

    @property
    def noncash_ntd(self):
        return max(self.recognized_ntd, max(0, self.expected_ntd - self.actual_ntd) if self.settled else 0)


@dataclass(frozen=True)
class ClientAccountingTransaction:
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None
