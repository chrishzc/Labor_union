"""Typed Payroll-owned readback used by the PAYOUT-002 current issue."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

PAYROLL_ANOMALY_OWNER_DOMAIN = "payroll"
PAYROLL_ANOMALY_OWNER_ROOT_TYPE = "payroll_obligation"
PAYOUT_002_SUBJECT_TYPE = "PAYOUT-002"


@dataclass(frozen=True, slots=True)
class PayrollLateObligationCurrentFact:
    obligation_identity: str
    source_event_identity: str
    owner_snapshot_token: str
    owner_version: int
    before_amount_ntd: int
    after_amount_ntd: int
    predicate_active: bool
    authoritative_complete: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.obligation_identity, "obligation identity", 191)
        require_canonical_text(self.source_event_identity, "source event identity", 191)
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_nonnegative_integer(self.before_amount_ntd, "before amount")
        require_nonnegative_integer(self.after_amount_ntd, "after amount")
        if not isinstance(self.predicate_active, bool) or not isinstance(self.authoritative_complete, bool):
            raise TypeError("Payroll late obligation flags must be bool")


__all__ = [
    "PAYROLL_ANOMALY_OWNER_DOMAIN",
    "PAYROLL_ANOMALY_OWNER_ROOT_TYPE",
    "PAYOUT_002_SUBJECT_TYPE",
    "PayrollLateObligationCurrentFact",
]
