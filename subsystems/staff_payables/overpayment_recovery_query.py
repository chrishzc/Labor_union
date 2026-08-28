"""
File: overpayment_recovery_query.py
Description: 提供 Staff Payables 追償根事實的嚴格唯讀查詢契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared_kernel.validation import require_canonical_text, require_positive_integer


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingView:
    matching_identity: str
    matching_version: int
    finance_import_row_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.matching_identity, "matching identity", 191)
        require_positive_integer(self.matching_version, "matching version")
        require_canonical_text(
            self.finance_import_row_identity, "finance import row identity", 191
        )


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryQueryView:
    staff_id: int
    recovery_identity: str
    remaining_amount_ntd: int
    status: str
    recovery_version: int
    staff_payables_version: int
    source_bank_fact_references: tuple[str, ...]
    source_payout_event_references: tuple[str, ...]
    source_obligation_references: tuple[str, ...]
    matchings: tuple[StaffOverpaymentRecoveryMatchingView, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff id")
        require_canonical_text(self.recovery_identity, "recovery identity", 191)
        if self.remaining_amount_ntd < 0:
            raise ValueError("staff_overpayment_recovery_query_invalid")
        for value, label in (
            (self.recovery_version, "recovery version"),
            (self.staff_payables_version, "staff payables version"),
        ):
            if value < 0:
                raise ValueError(f"{label} must be nonnegative")
        require_canonical_text(self.status, "recovery status", 32)
        if self.status not in {"open", "partially_recovered", "recovered", "adjusted"}:
            raise ValueError("staff_overpayment_recovery_query_invalid")
        if (self.status in {"open", "partially_recovered"}) != (
            self.remaining_amount_ntd > 0
        ):
            raise ValueError("staff_overpayment_recovery_query_invalid")
        matching_identities = [item.matching_identity for item in self.matchings]
        if len(matching_identities) != len(set(matching_identities)):
            raise ValueError("staff_overpayment_recovery_query_ambiguous")
        for refs, label in (
            (self.source_bank_fact_references, "source bank fact reference"),
            (self.source_payout_event_references, "source payout event reference"),
            (self.source_obligation_references, "source obligation reference"),
        ):
            for reference in refs:
                require_canonical_text(reference, label, 191)


class StaffOverpaymentRecoveryQueryRepository(Protocol):
    def query_recovery(
        self, staff_id: int, recovery_identity: str
    ) -> StaffOverpaymentRecoveryQueryView: ...


class StaffOverpaymentRecoveryQueryService:
    def __init__(self, repository: StaffOverpaymentRecoveryQueryRepository) -> None:
        self._repository = repository

    def query(self, staff_id: int, recovery_identity: str) -> StaffOverpaymentRecoveryQueryView:
        require_positive_integer(staff_id, "staff id")
        require_canonical_text(recovery_identity, "recovery identity", 191)
        return self._repository.query_recovery(staff_id, recovery_identity)


__all__ = [
    "StaffOverpaymentRecoveryMatchingView",
    "StaffOverpaymentRecoveryQueryRepository",
    "StaffOverpaymentRecoveryQueryService",
    "StaffOverpaymentRecoveryQueryView",
]
