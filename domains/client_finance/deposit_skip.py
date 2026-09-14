"""Rules for an auditable unpaid-deposit progression override."""

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class DepositSkipFacts:
    case_no: str
    account_version: int
    identity_status: str
    deposit_required_ntd: int
    deposit_net_received_ntd: int
    override_active: bool
    order_status: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case_no", 50)
        require_nonnegative_integer(self.account_version, "account_version")
        require_canonical_text(self.identity_status, "identity_status", 50)
        require_nonnegative_integer(self.deposit_required_ntd, "deposit_required_ntd")
        require_nonnegative_integer(self.deposit_net_received_ntd, "deposit_net_received_ntd")
        if not isinstance(self.override_active, bool):
            raise TypeError("override_active must be boolean")
        require_canonical_text(self.order_status, "order_status", 50)


@dataclass(frozen=True, slots=True)
class DepositSkipCandidate:
    case_no: str
    expected_account_version: int
    resulting_account_version: int
    deposit_required_ntd: int
    deposit_net_received_ntd: int
    override_active: bool
    mutates: bool
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint


def build_deposit_skip_candidate(facts: DepositSkipFacts) -> DepositSkipCandidate:
    blockers: list[str] = []
    if facts.identity_status != "一般市民":
        blockers.append("deposit_skip.general_citizen_required")
    if facts.deposit_required_ntd <= 0:
        blockers.append("deposit_skip.deposit_obligation_required")
    if facts.deposit_required_ntd > 0 and facts.deposit_net_received_ntd >= facts.deposit_required_ntd:
        blockers.append("deposit_skip.deposit_already_settled")
    if facts.order_status not in {"洽談中", "訂單成立"}:
        blockers.append("deposit_skip.order_status_not_eligible")
    # An existing finance override may still need its Orders projection repaired.
    mutates = not blockers and (not facts.override_active or facts.order_status == "洽談中")
    fingerprint = fingerprint_payload({
        "case_no": facts.case_no,
        "account_version": facts.account_version,
        "identity_status": facts.identity_status,
        "deposit_required_ntd": facts.deposit_required_ntd,
        "deposit_net_received_ntd": facts.deposit_net_received_ntd,
        "override_active": facts.override_active,
        "order_status": facts.order_status,
        "blockers": tuple(blockers),
        "mutates": mutates,
    })
    return DepositSkipCandidate(
        facts.case_no,
        facts.account_version,
        facts.account_version + (1 if mutates and not facts.override_active else 0),
        facts.deposit_required_ntd,
        facts.deposit_net_received_ntd,
        facts.override_active or mutates,
        mutates,
        tuple(blockers),
        fingerprint,
    )


__all__ = ["DepositSkipFacts", "DepositSkipCandidate", "build_deposit_skip_candidate"]
