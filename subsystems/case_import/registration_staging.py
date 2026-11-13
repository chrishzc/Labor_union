"""Typed pending questionnaire boundary; formal writes remain with Case Import/LINE."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol, TypedDict

from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from shared_kernel.identities import CorrelationId
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError


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
    def __init__(
        self,
        staging: RegistrationStagingPort,
        formal_application: FormalRegistrationApprovalPort,
        passbook_archiver=None,
    ) -> None:
        self._staging = staging
        self._formal = formal_application
        self._passbook_archiver = passbook_archiver

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
        self._archive_passbook_if_present(snapshot, receipt["client_id"], actor, correlation_id)
        completed = self._staging.complete(registration_id, snapshot.operation_id, receipt)
        self._delete_passbook_if_present(snapshot)
        return completed

    def reject_registration(self, registration_id, expected_version, actor):
        snapshot = self._staging.get(registration_id)
        rejected = self._staging.reject(registration_id, expected_version, actor)
        self._delete_passbook_if_present(snapshot)
        return rejected

    def passbook_image(self, registration_id: int):
        snapshot = self._staging.get(registration_id)
        image_id = _passbook_image_id(snapshot)
        if not image_id or not hasattr(self._staging, "get_passbook_image"):
            return None
        return self._staging.get_passbook_image(image_id)

    def _archive_passbook_if_present(self, snapshot, client_id: int, actor: str, correlation_id) -> None:
        image_id = _passbook_image_id(snapshot)
        if not image_id:
            return
        if self._passbook_archiver is None or not hasattr(self._staging, "get_passbook_image"):
            raise ProvisionalRegistrationStorageError("registration_passbook_archiver_unavailable")
        image = self._staging.get_passbook_image(image_id)
        if image is None:
            raise ProvisionalRegistrationStorageError("registration_passbook_image_missing")
        meta, content = image
        self._passbook_archiver(
            client_id=client_id,
            registration_id=snapshot.registration_id,
            filename=meta["filename"],
            mime_type=meta["mime_type"],
            content=content,
            actor=actor,
            correlation_id=correlation_id,
        )

    def _delete_passbook_if_present(self, snapshot) -> None:
        image_id = _passbook_image_id(snapshot)
        if image_id and hasattr(self._staging, "delete_passbook_image"):
            self._staging.delete_passbook_image(image_id)

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
                    self._archive_passbook_if_present(
                        snapshot,
                        receipt["client_id"],
                        snapshot.actor or "system:recovery",
                        CorrelationId(f"registration-recovery:{registration_id}"),
                    )
                    snapshot = self._staging.complete(registration_id, snapshot.operation_id, receipt)
                    self._delete_passbook_if_present(snapshot)
                if snapshot.status == "approved":
                    recovered += 1
            except Exception:
                # One blocked approval must not retain other committed questionnaires.
                failed += 1
        return RegistrationRecoveryResult(recovered, failed)


def _passbook_image_id(snapshot: StagedRegistration) -> str | None:
    if snapshot.candidate is None:
        return None
    survey = snapshot.candidate.beclass_payload.get("survey_details")
    if not isinstance(survey, dict):
        return None
    meta = survey.get("_liff_meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get("passbook_image_id")
    return str(value) if value else None
