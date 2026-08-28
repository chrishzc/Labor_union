"""
File: overpayment_query.py
Description: 提供政府補助溢撥根事實的唯讀、去敏與嚴格查詢契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


_PAYER_IDENTITY = "hccg"
_STATUSES = {
    "pending_review",
    "offset_reserved",
    "offset_applied",
    "return_payable",
    "partially_returned",
    "returned",
}


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOffsetTargetQueryView:
    claim_item_id: int
    claim_batch_id: int
    batch_version: int
    outstanding_amount_ntd: int
    payer_identity: str

    def __post_init__(self) -> None:
        if self.claim_item_id <= 0 or self.claim_batch_id <= 0:
            raise ValueError("government_subsidy_overpayment_query_invalid")
        require_nonnegative_integer(self.batch_version, "claim batch version")
        if isinstance(self.outstanding_amount_ntd, bool) or not isinstance(
            self.outstanding_amount_ntd, int
        ) or self.outstanding_amount_ntd <= 0:
            raise ValueError("government_subsidy_overpayment_target_not_eligible")
        require_canonical_text(self.payer_identity, "payer identity", 191)
        if self.payer_identity != _PAYER_IDENTITY:
            raise ValueError("government_subsidy_overpayment_cross_payer")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReturnRecipientQueryView:
    ready: bool
    blockers: tuple[str, ...]
    agency_identity: str | None = None
    agency_name: str | None = None
    bank_code: str | None = None
    account_display: str | None = None
    account_fingerprint: str | None = None
    effective_date: str | None = None

    def __post_init__(self) -> None:
        if self.blockers != tuple(sorted(set(self.blockers))):
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if self.ready and self.blockers:
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if not self.ready and any(
            value is not None
            for value in (
                self.agency_identity,
                self.agency_name,
                self.bank_code,
                self.account_display,
                self.account_fingerprint,
                self.effective_date,
            )
        ):
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if self.ready:
            for value, label in (
                (self.agency_identity, "agency identity"),
                (self.agency_name, "agency name"),
                (self.bank_code, "bank code"),
                (self.account_display, "masked account"),
                (self.account_fingerprint, "account fingerprint"),
                (self.effective_date, "effective date"),
            ):
                require_canonical_text(value or "", label, 191)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOverpaymentQueryView:
    overpayment_identity: str
    payer_identity: str
    remaining_amount_ntd: int
    status: str
    overpayment_version: int
    source_bank_fact_reference: str
    source_transaction_reference: str
    offset_targets: tuple[GovernmentSubsidyOffsetTargetQueryView, ...]
    return_recipient: GovernmentSubsidyReturnRecipientQueryView
    blockers: tuple[str, ...]
    available_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.overpayment_identity, "overpayment identity", 191)
        require_canonical_text(self.payer_identity, "payer identity", 191)
        if self.payer_identity != _PAYER_IDENTITY:
            raise ValueError("government_subsidy_overpayment_cross_payer")
        if isinstance(self.remaining_amount_ntd, bool) or not isinstance(
            self.remaining_amount_ntd, int
        ) or self.remaining_amount_ntd < 0:
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if self.status not in _STATUSES:
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if self.remaining_amount_ntd == 0 and self.status not in {
            "offset_applied",
            "returned",
        }:
            raise ValueError("government_subsidy_overpayment_query_invalid")
        require_nonnegative_integer(self.overpayment_version, "overpayment version")
        require_canonical_text(
            self.source_bank_fact_reference, "source bank fact reference", 191
        )
        require_canonical_text(
            self.source_transaction_reference, "source transaction reference", 191
        )
        identities = [item.claim_item_id for item in self.offset_targets]
        if len(identities) != len(set(identities)):
            raise ValueError("government_subsidy_overpayment_target_ambiguous")
        if self.blockers != tuple(sorted(set(self.blockers))):
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if self.available_actions != tuple(sorted(set(self.available_actions))):
            raise ValueError("government_subsidy_overpayment_query_invalid")
        if any(action not in {"offset", "return"} for action in self.available_actions):
            raise ValueError("government_subsidy_overpayment_query_invalid")


class GovernmentSubsidyOverpaymentQueryRepository(Protocol):
    def query_overpayment(
        self, overpayment_identity: str
    ) -> GovernmentSubsidyOverpaymentQueryView | None: ...


class GovernmentSubsidyOverpaymentQueryError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class GovernmentSubsidyOverpaymentQueryWorkflow:
    def __init__(self, repository: GovernmentSubsidyOverpaymentQueryRepository) -> None:
        self._repository = repository

    def query(
        self, overpayment_identity: str, correlation_id: CorrelationId
    ) -> GovernmentSubsidyOverpaymentQueryView:
        require_canonical_text(overpayment_identity, "overpayment identity", 191)
        try:
            result = self._repository.query_overpayment(overpayment_identity)
        except GovernmentSubsidyOverpaymentQueryError:
            raise
        except ValueError as error:
            raise _query_error(
                correlation_id,
                str(error) or "government_subsidy_overpayment_query_invalid",
            ) from error
        if result is None:
            raise _query_error(
                correlation_id, "government_subsidy_overpayment_not_found"
            )
        if result.overpayment_identity != overpayment_identity:
            raise _query_error(
                correlation_id, "government_subsidy_overpayment_owner_mismatch"
            )
        if result.payer_identity != _PAYER_IDENTITY:
            raise _query_error(
                correlation_id, "government_subsidy_overpayment_cross_payer"
            )
        return result


def _query_error(
    correlation_id: CorrelationId, code: str
) -> GovernmentSubsidyOverpaymentQueryError:
    category = (
        ErrorCategory.NOT_FOUND
        if code.endswith("not_found")
        else ErrorCategory.CONFLICT
    )
    return GovernmentSubsidyOverpaymentQueryError(
        TypedError(
            category,
            code,
            "政府補助溢撥根事實查詢未完成。",
            correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.CONFLICT else (),
        )
    )


__all__ = [
    "GovernmentSubsidyOffsetTargetQueryView",
    "GovernmentSubsidyOverpaymentQueryError",
    "GovernmentSubsidyOverpaymentQueryRepository",
    "GovernmentSubsidyOverpaymentQueryView",
    "GovernmentSubsidyOverpaymentQueryWorkflow",
    "GovernmentSubsidyReturnRecipientQueryView",
]
