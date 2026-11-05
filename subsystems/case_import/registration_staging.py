"""Typed pending questionnaire boundary; formal writes remain with Case Import/LINE."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol, TypedDict

from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from shared_kernel.identities import CorrelationId


class RegistrationApprovalReceipt(TypedDict):
    client_id: int
    beclass_record_id: int
    case_no: str | None
    approved_at_utc: str


@dataclass(frozen=True, slots=True)
class RegistrationRecoveryResult:
    recovered: int
    failed: int


@dataclass(frozen=True, slots=True, repr=False)
class StagedRegistration:
    registration_id: int
    version: int
    status: str
    submitted_at_utc: datetime
    expires_at_utc: datetime
    registration_kind: str
    candidate: ProvisionalRegistrationCandidate | None = None
    operation_id: str | None = None
    actor: str | None = None
    client_id: int | None = None
    beclass_record_id: int | None = None
    case_no: str | None = None
    approved_at_utc: datetime | None = None
    replayed: bool = False


class RegistrationStagingPort(Protocol):
    def submit(self, candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration: ...
    def get(self, registration_id: int) -> StagedRegistration: ...
    def pending(self, *, after_id: int = 0, limit: int = 50) -> tuple[StagedRegistration, ...]: ...
    def claim_approval(self, registration_id: int, expected_version: int, actor: str) -> StagedRegistration: ...
    def reject(self, registration_id: int, expected_version: int, actor: str) -> StagedRegistration: ...
    def complete(self, registration_id: int, operation_id: str, receipt: RegistrationApprovalReceipt) -> StagedRegistration: ...
    def processing_ids(self, *, limit: int = 100) -> tuple[int, ...]: ...


class FormalRegistrationApprovalPort(Protocol):
    def registration_approval_receipt(self, registration_id: int, operation_id: str) -> RegistrationApprovalReceipt | None: ...
    def approve_staged_registration(self, staged: StagedRegistration, correlation_id: CorrelationId) -> RegistrationApprovalReceipt: ...


class RegistrationReviewApplication:
    def __init__(self, staging: RegistrationStagingPort, formal_application: FormalRegistrationApprovalPort) -> None:
        self._staging = staging
        self._formal = formal_application

    def pending_registrations(self, *, after_id=0, limit=50):
        return self._staging.pending(after_id=after_id, limit=limit)

    def registration_application(self, registration_id):
        snapshot = self._staging.get(registration_id)
        if snapshot.status == "approving":
            # Query remains read-only. Recovery is owned by POST or the internal worker.
            receipt = self._formal.registration_approval_receipt(registration_id, snapshot.operation_id)
            if receipt is not None:
                return replace(snapshot, candidate=None, client_id=receipt["client_id"],
                    beclass_record_id=receipt["beclass_record_id"], case_no=receipt["case_no"],
                    approved_at_utc=datetime.fromisoformat(receipt["approved_at_utc"]))
        return snapshot

    def approve_registration(self, registration_id, expected_version, actor, correlation_id):
        snapshot = self._staging.claim_approval(registration_id, expected_version, actor)
        if snapshot.status == "approved":
            return snapshot
        # The same registration/operation is the only allowed recovery path.
        receipt = self._formal.approve_staged_registration(snapshot, correlation_id)
        return self._staging.complete(registration_id, snapshot.operation_id, receipt)

    def reject_registration(self, registration_id, expected_version, actor):
        return self._staging.reject(registration_id, expected_version, actor)

    def recover(self, *, limit=100):
        recovered = failed = 0
        for registration_id in self._staging.processing_ids(limit=limit):
            try:
                snapshot = self._staging.get(registration_id)
                receipt = self._formal.registration_approval_receipt(registration_id, snapshot.operation_id)
                if snapshot.status == "approving" and receipt is None:
                    receipt = self._formal.approve_staged_registration(snapshot,
                        CorrelationId(f"registration-recovery:{registration_id}"))
                if receipt is not None:
                    snapshot = self._staging.complete(registration_id, snapshot.operation_id, receipt)
                if snapshot.status == "approved":
                    recovered += 1
            except Exception:
                # One blocked approval must not retain other committed questionnaires.
                failed += 1
        return RegistrationRecoveryResult(recovered, failed)
