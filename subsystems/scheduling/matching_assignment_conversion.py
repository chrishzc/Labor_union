"""
File: matching_assignment_conversion.py
Description: 驗證、提交並查詢 M3 typed assignment conversion；不寫入 owning roots。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domains.scheduling.matching_coordination import (
    MatchingCrossDomainRequest,
    MatchingRequestKind,
    MatchingSourceTuple,
    canonical_source_tuple,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from subsystems.scheduling.matching_coordination_contracts import typed_error


@dataclass(frozen=True, slots=True)
class AssignmentConversionSubmitCommand:
    request: MatchingCrossDomainRequest
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if not isinstance(self.request, MatchingCrossDomainRequest):
            raise TypeError("assignment conversion request must be MatchingCrossDomainRequest")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("assignment conversion idempotency_key must be IdempotencyKey")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("assignment conversion correlation_id must be CorrelationId")

    @property
    def fingerprint(self) -> PreviewFingerprint:
        request = self.request
        return fingerprint_payload(
            {
                "request_id": request.request_id,
                "request_kind": request.request_kind.value,
                "case_no": request.case_no,
                "package_id": request.package_id,
                "package_version": request.package_version,
                "criteria_snapshot_id": request.criteria_snapshot_id,
                "candidate_id": request.candidate_id,
                "source_versions": tuple(item.as_payload() for item in request.source_versions),
                "lineage_event_id": request.lineage_event_id,
                "reason": request.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class AssignmentConversionSubmissionReceipt:
    request_id: str
    durable_reference: str
    request_fingerprint: PreviewFingerprint
    replayed: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.request_id, "assignment conversion request ID", 191)
        require_canonical_text(self.durable_reference, "assignment conversion durable reference", 191)
        if not isinstance(self.request_fingerprint, PreviewFingerprint):
            raise TypeError("assignment conversion request_fingerprint must be PreviewFingerprint")
        if not isinstance(self.replayed, bool):
            raise TypeError("assignment conversion replayed must be bool")


class AssignmentConversionResultState(StrEnum):
    CONVERTED = "converted"
    REMATCH_REQUIRED = "rematch_required"


@dataclass(frozen=True, slots=True)
class CanonicalAssignmentConversionReceipt:
    request_id: str
    result_state: AssignmentConversionResultState
    package_id: str
    package_version: int
    criteria_snapshot_id: str
    candidate_id: str
    source_versions: MatchingSourceTuple
    assignment_reference: str | None
    receipt_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        require_canonical_text(self.request_id, "assignment conversion request ID", 191)
        require_canonical_text(self.package_id, "assignment conversion package ID", 191)
        require_nonnegative_integer(self.package_version, "assignment conversion package version")
        require_canonical_text(self.criteria_snapshot_id, "assignment conversion criteria snapshot ID", 191)
        require_canonical_text(self.candidate_id, "assignment conversion candidate ID", 191)
        if not isinstance(self.result_state, AssignmentConversionResultState):
            object.__setattr__(self, "result_state", AssignmentConversionResultState(self.result_state))
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if not isinstance(self.receipt_fingerprint, PreviewFingerprint):
            raise TypeError("assignment conversion receipt_fingerprint must be PreviewFingerprint")
        if self.result_state is AssignmentConversionResultState.CONVERTED:
            require_canonical_text(self.assignment_reference, "assignment conversion assignment reference", 191)
        elif self.assignment_reference is not None:
            raise ValueError("rematch-required conversion receipt cannot contain assignment reference")


class AssignmentConversionRequestPort(Protocol):
    def submit(self, command: AssignmentConversionSubmitCommand) -> AssignmentConversionSubmissionReceipt: ...


class AssignmentConversionQueryPort(Protocol):
    def get_canonical_receipt(self, request_id: str) -> CanonicalAssignmentConversionReceipt | None: ...


class MatchingAssignmentConversionError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class MatchingAssignmentConversion:
    def __init__(
        self,
        request_port: AssignmentConversionRequestPort,
        query_port: AssignmentConversionQueryPort,
    ) -> None:
        self._request_port = request_port
        self._query_port = query_port

    def submit(self, command: AssignmentConversionSubmitCommand) -> AssignmentConversionSubmissionReceipt:
        request = command.request
        if (
            request.request_kind is not MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED
            or request.candidate_id is None
        ):
            raise self._mismatch(command.correlation_id)
        try:
            receipt = self._request_port.submit(command)
        except Exception as error:
            raise MatchingAssignmentConversionError(
                typed_error(
                    "matching_transaction_failed",
                    command.correlation_id,
                    category=ErrorCategory.UNAVAILABLE,
                    retryable=True,
                )
            ) from error
        if (
            not isinstance(receipt, AssignmentConversionSubmissionReceipt)
            or receipt.request_id != request.request_id
            or receipt.request_fingerprint != command.fingerprint
        ):
            raise self._mismatch(command.correlation_id)
        return receipt

    def query(
        self,
        request: MatchingCrossDomainRequest,
        correlation_id: CorrelationId,
    ) -> CanonicalAssignmentConversionReceipt:
        if not isinstance(request, MatchingCrossDomainRequest):
            raise TypeError("assignment conversion query request must be MatchingCrossDomainRequest")
        if not isinstance(correlation_id, CorrelationId):
            raise TypeError("assignment conversion query correlation_id must be CorrelationId")
        if (
            request.request_kind is not MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED
            or request.candidate_id is None
        ):
            raise self._mismatch(correlation_id)
        try:
            receipt = self._query_port.get_canonical_receipt(request.request_id)
        except Exception as error:
            raise self._transaction_failed(correlation_id) from error
        if receipt is None:
            raise MatchingAssignmentConversionError(
                typed_error("matching_assignment_conversion_pending", correlation_id)
            )
        if (
            not isinstance(receipt, CanonicalAssignmentConversionReceipt)
            or receipt.request_id != request.request_id
            or receipt.package_id != request.package_id
            or receipt.package_version != request.package_version
            or receipt.criteria_snapshot_id != request.criteria_snapshot_id
            or receipt.candidate_id != request.candidate_id
            or receipt.source_versions != request.source_versions
        ):
            raise self._mismatch(correlation_id)
        return receipt

    @staticmethod
    def _mismatch(correlation_id: CorrelationId) -> MatchingAssignmentConversionError:
        return MatchingAssignmentConversionError(
            typed_error("matching_assignment_conversion_mismatch", correlation_id)
        )

    @staticmethod
    def _transaction_failed(correlation_id: CorrelationId) -> MatchingAssignmentConversionError:
        return MatchingAssignmentConversionError(
            typed_error(
                "matching_transaction_failed",
                correlation_id,
                category=ErrorCategory.UNAVAILABLE,
                retryable=True,
            )
        )


__all__ = [
    "AssignmentConversionQueryPort",
    "AssignmentConversionRequestPort",
    "AssignmentConversionResultState",
    "AssignmentConversionSubmissionReceipt",
    "AssignmentConversionSubmitCommand",
    "CanonicalAssignmentConversionReceipt",
    "MatchingAssignmentConversion",
    "MatchingAssignmentConversionError",
]
