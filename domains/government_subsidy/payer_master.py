"""Government payer master facts and versioned refund-account rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text

PAYER_IDENTITY = "hccg"
PAYER_NAME = "新竹市政府"
_TEXT_MAX = 191


class GovernmentPayerMasterError(ValueError):
    """Stable errors for the government payer master."""


@dataclass(frozen=True, slots=True)
class GovernmentRefundAccount:
    bank_code: str
    account_number: str
    account_name: str
    effective_from: date
    reason: str
    evidence_reference: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.bank_code, "bank code"),
            (self.account_number, "account number"),
            (self.account_name, "account name"),
            (self.reason, "reason"),
            (self.evidence_reference, "evidence reference"),
        ):
            require_canonical_text(value, label, _TEXT_MAX)
        if not isinstance(self.effective_from, date):
            raise GovernmentPayerMasterError("government_payer_account_effective_date_invalid")


@dataclass(frozen=True, slots=True)
class GovernmentRefundAccountVersion:
    account: GovernmentRefundAccount
    effective_until: date | None


@dataclass(frozen=True, slots=True)
class GovernmentPayerMaster:
    payer_identity: str
    payer_name: str
    active_account: GovernmentRefundAccountVersion | None

    def __post_init__(self) -> None:
        if self.payer_identity != PAYER_IDENTITY or self.payer_name != PAYER_NAME:
            raise GovernmentPayerMasterError("government_payer_not_found")


@dataclass(frozen=True, slots=True)
class GovernmentRefundAccountPreview:
    payer_identity: str
    account: GovernmentRefundAccount
    previous_effective_from: date | None
    fingerprint: PreviewFingerprint


def build_refund_account_preview(
    master: GovernmentPayerMaster,
    account: GovernmentRefundAccount,
) -> GovernmentRefundAccountPreview:
    previous = master.active_account
    if previous is not None and account.effective_from <= previous.account.effective_from:
        raise GovernmentPayerMasterError("government_payer_account_effective_date_invalid")
    fingerprint = fingerprint_payload({
        "payer_identity": master.payer_identity,
        "previous_effective_from": _date_value(previous.account.effective_from) if previous else None,
        "account": _account_payload(account),
    })
    return GovernmentRefundAccountPreview(
        master.payer_identity, account,
        previous.account.effective_from if previous else None, fingerprint,
    )


def _account_payload(account: GovernmentRefundAccount) -> dict[str, str]:
    return {
        "bank_code": account.bank_code,
        "account_number": account.account_number,
        "account_name": account.account_name,
        "effective_from": _date_value(account.effective_from),
        "reason": account.reason,
        "evidence_reference": account.evidence_reference,
    }


def _date_value(value: date) -> str:
    return value.isoformat()

