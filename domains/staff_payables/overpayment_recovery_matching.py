"""Immutable human matching of a staff return bank fact to a recovery root."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingCandidate:
    recovery_identity: str
    staff_id: int
    finance_import_row_identity: str
    recovery_version: int
    staff_payables_version: int
    fingerprint: PreviewFingerprint


def build_staff_overpayment_recovery_matching_candidate(
    *, recovery_identity: str, staff_id: int, finance_import_row_identity: str,
    recovery_version: int, staff_payables_version: int, bank_fact_eligible: bool,
) -> StaffOverpaymentRecoveryMatchingCandidate:
    require_canonical_text(recovery_identity, "staff recovery identity", 191)
    require_canonical_text(finance_import_row_identity, "finance import row identity", 191)
    if not isinstance(staff_id, int) or staff_id <= 0:
        raise ValueError("staff_overpayment_recovery_target_ambiguous")
    if not bank_fact_eligible:
        raise ValueError("bank_fact_not_eligible")
    require_nonnegative_integer(recovery_version, "staff recovery version")
    require_nonnegative_integer(staff_payables_version, "staff payables version")
    return StaffOverpaymentRecoveryMatchingCandidate(
        recovery_identity, staff_id, finance_import_row_identity, recovery_version,
        staff_payables_version,
        fingerprint_payload({
            "recovery_identity": recovery_identity, "staff_id": staff_id,
            "finance_import_row_identity": finance_import_row_identity,
            "recovery_version": recovery_version,
            "staff_payables_version": staff_payables_version,
        }),
    )
