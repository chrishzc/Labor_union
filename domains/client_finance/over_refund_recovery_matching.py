"""Rules for a human-confirmed incoming-bank to recovery assignment."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatching:
    identity: str
    case_no: str
    recovery_identity: str
    finance_import_row_identity: str
    recovery_version: int
    account_version: int
    version: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.identity, "matching identity"),
            (self.case_no, "case number"),
            (self.recovery_identity, "recovery identity"),
            (self.finance_import_row_identity, "finance import row identity"),
        ):
            require_canonical_text(value, label, 191)
        for value, label in (
            (self.recovery_version, "recovery version"),
            (self.account_version, "account version"),
            (self.version, "matching version"),
        ):
            require_nonnegative_integer(value, label)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingCandidate:
    case_no: str
    recovery_identity: str
    finance_import_row_identity: str
    recovery_version: int
    account_version: int
    fingerprint: PreviewFingerprint


def build_client_over_refund_recovery_matching_candidate(
    *,
    case_no: str,
    recovery_identity: str,
    finance_import_row_identity: str,
    recovery_version: int,
    account_version: int,
    bank_fact_eligible: bool,
) -> ClientOverRefundRecoveryMatchingCandidate:
    """A match records human evidence; it neither reconciles cash nor changes recovery."""
    for value, label in (
        (case_no, "case number"),
        (recovery_identity, "recovery identity"),
        (finance_import_row_identity, "finance import row identity"),
    ):
        require_canonical_text(value, label, 191)
    if not bank_fact_eligible:
        raise ValueError("bank_fact_not_eligible")
    require_nonnegative_integer(recovery_version, "recovery version")
    require_nonnegative_integer(account_version, "account version")
    return ClientOverRefundRecoveryMatchingCandidate(
        case_no,
        recovery_identity,
        finance_import_row_identity,
        recovery_version,
        account_version,
        fingerprint_payload(
            {
                "case_no": case_no,
                "recovery_identity": recovery_identity,
                "finance_import_row_identity": finance_import_row_identity,
                "recovery_version": recovery_version,
                "account_version": account_version,
            }
        ),
    )


__all__ = [name for name in globals() if name.startswith("ClientOverRefundRecovery") or name.startswith("build_client")]
