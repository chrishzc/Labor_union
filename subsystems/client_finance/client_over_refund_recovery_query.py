"""
File: client_over_refund_recovery_query.py
Description: 提供客戶退款超額追償的唯讀、去敏與嚴格 owner Query。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryQuerySelection:
    case_no: str
    recovery_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        require_canonical_text(self.recovery_identity, "recovery identity", 191)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingQueryFact:
    matching_identity: str
    matching_version: int
    incoming_row_reference: str

    def __post_init__(self) -> None:
        require_canonical_text(self.matching_identity, "matching identity", 191)
        require_nonnegative_integer(self.matching_version, "matching version")
        require_canonical_text(self.incoming_row_reference, "incoming row reference", 191)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryQueryFacts:
    case_no: str
    recovery_identity: str
    remaining_amount_ntd: int
    status: str
    recovery_version: int
    account_version: int
    source_row_reference: str
    current_matchings: tuple[ClientOverRefundRecoveryMatchingQueryFact, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        require_canonical_text(self.recovery_identity, "recovery identity", 191)
        if (isinstance(self.remaining_amount_ntd, bool)
                or not isinstance(self.remaining_amount_ntd, int)
                or self.remaining_amount_ntd < 0):
            raise ValueError("client_over_refund_recovery_query_invalid")
        if self.status not in {"open", "partially_recovered", "recovered", "adjusted"}:
            raise ValueError("client_over_refund_recovery_query_invalid")
        if (self.status in {"open", "partially_recovered"}) != (
            self.remaining_amount_ntd > 0
        ):
            raise ValueError("client_over_refund_recovery_query_invalid")
        require_nonnegative_integer(self.recovery_version, "recovery version")
        require_nonnegative_integer(self.account_version, "account version")
        require_canonical_text(self.source_row_reference, "source row reference", 191)
        identities = [item.matching_identity for item in self.current_matchings]
        if len(identities) != len(set(identities)):
            raise ValueError("client_over_refund_recovery_query_ambiguous")


class ClientOverRefundRecoveryQueryRepository(Protocol):
    def query_recovery(
        self, selection: ClientOverRefundRecoveryQuerySelection
    ) -> ClientOverRefundRecoveryQueryFacts | None: ...


class ClientOverRefundRecoveryQueryError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class ClientOverRefundRecoveryQueryWorkflow:
    def __init__(self, repository: ClientOverRefundRecoveryQueryRepository) -> None:
        self._repository = repository

    def query(
        self, selection: ClientOverRefundRecoveryQuerySelection, correlation_id: CorrelationId
    ) -> ClientOverRefundRecoveryQueryFacts:
        try:
            facts = self._repository.query_recovery(selection)
        except ClientOverRefundRecoveryQueryError:
            raise
        except ValueError as error:
            raise _query_error(correlation_id, str(error) or "client_over_refund_recovery_query_invalid") from error
        if facts is None:
            raise _query_error(correlation_id, "client_over_refund_recovery_not_found")
        if facts.case_no != selection.case_no or facts.recovery_identity != selection.recovery_identity:
            raise _query_error(correlation_id, "client_over_refund_recovery_owner_mismatch")
        return facts


def _query_error(correlation_id: CorrelationId, code: str) -> ClientOverRefundRecoveryQueryError:
    category = ErrorCategory.NOT_FOUND if code.endswith("not_found") else ErrorCategory.CONFLICT
    return ClientOverRefundRecoveryQueryError(
        TypedError(category, code, "Client over-refund recovery query cannot be completed.", correlation_id,
                   domain_blockers=(code,) if category is ErrorCategory.CONFLICT else ())
    )


__all__ = [name for name in globals() if name.startswith("ClientOverRefundRecovery")]
