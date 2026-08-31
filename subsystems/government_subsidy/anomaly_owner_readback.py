"""Government Subsidy-owned readback contract for GOVSUB-003/005/007.

The service is intentionally a closed dispatcher.  It does not resolve issues,
write Anomalies state, or provide a generic compensation/update operation.
"""

from __future__ import annotations

from typing import Protocol, TypeAlias

from domains.government_subsidy.anomaly_remediation import (
    GovernmentSubsidyClaimDriftOwnerFact,
    GovernmentSubsidyIntegrityOwnerFact,
    GovernmentSubsidyRecoveryRoot,
)
from shared_kernel.validation import require_canonical_text


GovernmentSubsidyOwnerFact: TypeAlias = (
    GovernmentSubsidyIntegrityOwnerFact
    | GovernmentSubsidyClaimDriftOwnerFact
    | GovernmentSubsidyRecoveryRoot
)


class GovernmentSubsidyAnomalyOwnerRepository(Protocol):
    """Read-only owner repository; implementations must not commit or mutate."""

    def read_integrity(self, batch_id: int) -> GovernmentSubsidyIntegrityOwnerFact: ...

    def read_claim_drift(self, claim_item_id: int) -> GovernmentSubsidyClaimDriftOwnerFact: ...

    def read_return_overage(self, payable_identity: str) -> GovernmentSubsidyRecoveryRoot | None: ...


class GovernmentSubsidyAnomalyOwnerReadback:
    """Dispatch each current issue to its Government Subsidy owner readback."""

    def __init__(self, repository: GovernmentSubsidyAnomalyOwnerRepository) -> None:
        self._repository = repository

    def read(self, definition_code: str, subject_identity: str) -> GovernmentSubsidyOwnerFact:
        require_canonical_text(definition_code, "definition code", 32)
        require_canonical_text(subject_identity, "subject identity", 191)
        if definition_code == "GOVSUB-003":
            batch_id = _positive_decimal(subject_identity, "batch id")
            fact = self._repository.read_integrity(batch_id)
            if fact.batch_id != batch_id:
                raise ValueError("government_subsidy_owner_mismatch")
            return fact
        if definition_code == "GOVSUB-005":
            claim_item_id = _claim_item_id(subject_identity)
            fact = self._repository.read_claim_drift(claim_item_id)
            if fact.claim_item_id != claim_item_id:
                raise ValueError("government_subsidy_owner_mismatch")
            return fact
        if definition_code == "GOVSUB-007":
            fact = self._repository.read_return_overage(subject_identity)
            if fact is None:
                raise ValueError("government_subsidy_recovery_not_found")
            if fact.original_return_obligation_identity != subject_identity:
                raise ValueError("government_subsidy_owner_mismatch")
            return fact
        raise ValueError("government_subsidy_owner_issue_not_supported")


def _positive_decimal(value: str, label: str) -> int:
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _claim_item_id(value: str) -> int:
    # The public issue identity is assignment_id:batch_id:claim_item_id.
    # Accepting the legacy bare claim-item form keeps readback compatible with
    # the pre-convergence projection while still validating all new coordinates.
    parts = value.split(":")
    if len(parts) == 1:
        return _positive_decimal(value, "claim item id")
    if len(parts) != 3 or any(not part.isdecimal() or int(part) <= 0 for part in parts):
        raise ValueError("claim drift subject identity is invalid")
    return int(parts[2])


__all__ = [
    "GovernmentSubsidyAnomalyOwnerRepository",
    "GovernmentSubsidyAnomalyOwnerReadback",
    "GovernmentSubsidyOwnerFact",
]
