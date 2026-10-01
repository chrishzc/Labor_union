"""
File: hcm_resubmission_workflow.py
Description: 編排 HCM 單一警示欄位修正的 Preview、Apply、receipt 與 owner outbox。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Callable, Mapping, Protocol

from domains.case_import.hcm_resubmission import (
    HcmFieldCorrectionCandidate,
    HcmResubmissionFacts,
    build_hcm_field_correction_candidate,
)
from domains.clients.hcm_correction import ClientHcmCorrectionCommand
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from domains.case_import.hcm_import_review import HCM_SKIP_REJECT_REASON_PATH, validate_missing_reject_reason_skip


@dataclass(frozen=True, slots=True)
class HcmReviewSkipFacts:
    review_identity: str
    case_no: str
    review_version: int
    source_fingerprint: str
    issue_codes: tuple[str, ...]
    reject_reason: str | None
    already_skipped: bool
    is_current: bool


@dataclass(frozen=True, slots=True)
class HcmReviewSkipPreview:
    review_identity: str
    case_no: str
    source_field: str
    review_version: int
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class ApplyHcmReviewSkip:
    review_identity: str
    expected_review_version: int
    preview_fingerprint: str
    idempotency_key: str
    actor: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class HcmResubmissionSource:
    corrected_record: Mapping[str, object]
    validation_errors: Mapping[str, str]
    target_values: Mapping[str, object]
    source_event_identity: str
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class HcmResubmissionPreview:
    review_identity: str
    case_no: str
    source_field: str
    target_fields: tuple[str, ...]
    review_version: int
    root_fingerprint: str
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class ApplyHcmResubmission:
    review_identity: str
    source: HcmResubmissionSource
    expected_review_version: int
    expected_root_fingerprint: str
    preview_fingerprint: str
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class HcmResubmissionReceipt:
    event_identity: str
    review_identity: str
    case_no: str
    target_fields: tuple[str, ...]
    resulting_review_version: int
    replayed: bool


class HcmResubmissionRepository(Protocol):
    def load_skip_facts(self, review_identity: str, *, for_update: bool) -> HcmReviewSkipFacts: ...

    def apply_skip(self, facts: HcmReviewSkipFacts, request: ApplyHcmReviewSkip) -> str: ...
    def query_review(self, review_identity: str) -> Mapping[str, object]: ...

    def query_current_reviews(self, *, limit: int, before_id: int | None) -> Mapping[str, object]: ...

    def load_facts(self, review_identity: str, *, for_update: bool) -> HcmResubmissionFacts: ...

    def readback(self, case_no: str) -> Mapping[str, object]: ...

    def find_receipt(self, idempotency_key: str, *, for_update: bool = False) -> tuple[str, HcmResubmissionReceipt] | None: ...

    def apply_field_correction(
        self,
        candidate: HcmFieldCorrectionCandidate,
        source: HcmResubmissionSource,
        *,
        actor: str,
        reason: str,
        correlation_id: str,
    ) -> str: ...

    def save_receipt(
        self,
        idempotency_key: str,
        command_fingerprint: str,
        preview_fingerprint: str,
        receipt: HcmResubmissionReceipt,
    ) -> None: ...

    def append_outbox(self, event_identity: str, review_identity: str) -> None: ...


def _skip_preview(facts: HcmReviewSkipFacts) -> HcmReviewSkipPreview:
    validate_missing_reject_reason_skip(issue_codes=facts.issue_codes, reject_reason=facts.reject_reason,
                                       already_skipped=facts.already_skipped, is_current=facts.is_current)
    fingerprint = fingerprint_payload({
        "operation": HCM_SKIP_REJECT_REASON_PATH, "review_identity": facts.review_identity,
        "case_no": facts.case_no, "review_version": facts.review_version,
        "source_fingerprint": facts.source_fingerprint,
    }).value
    return HcmReviewSkipPreview(facts.review_identity, facts.case_no, "不符合原因",
                               facts.review_version, fingerprint)


class HcmResubmissionConflict(ValueError):
    pass


class HcmResubmissionWorkflow:
    def __init__(self, repository: HcmResubmissionRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_review(self, review_identity: str):
        return self._repository.query_review(review_identity)

    def preview_skip(self, review_identity: str) -> HcmReviewSkipPreview:
        return _skip_preview(self._repository.load_skip_facts(review_identity, for_update=False))

    def apply_skip(self, request: ApplyHcmReviewSkip) -> HcmResubmissionReceipt:
        command_fingerprint = fingerprint_payload({
            "operation": HCM_SKIP_REJECT_REASON_PATH, "review_identity": request.review_identity,
            "expected_review_version": request.expected_review_version,
            "preview_fingerprint": request.preview_fingerprint, "actor": request.actor,
        }).value
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise HcmResubmissionConflict("hcm_resubmission_idempotency_conflict")
                return replace(receipt, replayed=True)
            facts = self._repository.load_skip_facts(request.review_identity, for_update=True)
            replay = self._repository.find_receipt(request.idempotency_key, for_update=True)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise HcmResubmissionConflict("hcm_resubmission_idempotency_conflict")
                return replace(receipt, replayed=True)
            if facts.review_version != request.expected_review_version:
                raise HcmResubmissionConflict("hcm_review_skip_version_conflict")
            try:
                preview = _skip_preview(facts)
            except ValueError as error:
                raise HcmResubmissionConflict("hcm_review_skip_stale") from error
            if preview.preview_fingerprint != request.preview_fingerprint:
                raise HcmResubmissionConflict("hcm_review_skip_stale")
            event_identity = self._repository.apply_skip(facts, request)
            receipt = HcmResubmissionReceipt(event_identity, facts.review_identity, facts.case_no,
                                            (HCM_SKIP_REJECT_REASON_PATH,), facts.review_version + 1, False)
            self._repository.save_receipt(request.idempotency_key, command_fingerprint,
                                          preview.preview_fingerprint, receipt)
            self._repository.append_outbox(event_identity, facts.review_identity)
            unit_of_work.commit()
        return receipt

    def query_current_reviews(self, *, limit: int, before_id: int | None):
        return self._repository.query_current_reviews(limit=limit, before_id=before_id)

    def preview(self, review_identity: str, source: HcmResubmissionSource) -> HcmResubmissionPreview:
        facts = self._repository.load_facts(review_identity, for_update=False)
        candidate = _candidate(facts, source)
        return _preview(facts, candidate, source)

    def facts(self, review_identity: str) -> HcmResubmissionFacts:
        """Read only canonical review facts for owner input selection."""
        return self._repository.load_facts(review_identity, for_update=False)

    def apply(self, request: ApplyHcmResubmission) -> HcmResubmissionReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise HcmResubmissionConflict("hcm_resubmission_idempotency_conflict")
                return replace(receipt, replayed=True)
            facts = self._repository.load_facts(request.review_identity, for_update=True)
            _validate_versions(request, facts)
            candidate = _candidate(facts, request.source)
            preview = _preview(facts, candidate, request.source)
            if preview.preview_fingerprint != request.preview_fingerprint:
                raise HcmResubmissionConflict("hcm_resubmission_preview_stale")
            event_identity = self._repository.apply_field_correction(
                candidate,
                request.source,
                actor=request.actor,
                reason=request.reason,
                correlation_id=request.correlation_id,
                client_command=_client_command(facts, candidate, request),
            )
            receipt = HcmResubmissionReceipt(
                event_identity,
                candidate.review_identity,
                candidate.case_no,
                candidate.target_fields,
                facts.review_version + 1,
                False,
            )
            self._repository.save_receipt(
                request.idempotency_key,
                command_fingerprint,
                preview.preview_fingerprint,
                receipt,
            )
            self._repository.append_outbox(event_identity, candidate.review_identity)
            # Read the authoritative Client and Orders roots while this same
            # outer transaction is still open.  A mismatch must raise here so
            # the UoW context rolls back the event, receipt, and outbox rather
            # than reporting a committed correction that cannot be verified.
            _verify_readback(self._repository.readback(candidate.case_no), facts, candidate)
            unit_of_work.commit()
            return receipt


def _candidate(facts: HcmResubmissionFacts, source: HcmResubmissionSource) -> HcmFieldCorrectionCandidate:
    return build_hcm_field_correction_candidate(
        facts,
        source.corrected_record,
        source.validation_errors,
        source.target_values,
    )


def hcm_resubmission_source_event_identity(
    review_identity: str,
    workbook_fingerprint: str,
) -> str:
    """Scope a corrected workbook event to one canonical review."""
    if not review_identity.strip() or len(workbook_fingerprint) != 64:
        raise ValueError("hcm_resubmission_source_identity_invalid")
    return "hcm-resubmission:" + hashlib.sha256(
        f"{review_identity}:{workbook_fingerprint}".encode("utf-8")
    ).hexdigest()


def _preview(
    facts: HcmResubmissionFacts,
    candidate: HcmFieldCorrectionCandidate,
    source: HcmResubmissionSource,
) -> HcmResubmissionPreview:
    fingerprint = fingerprint_payload({
        "candidate": {
            "case_no": candidate.case_no,
            "review_identity": candidate.review_identity,
            "source_field": candidate.source_field,
            "target_fields": candidate.target_fields,
            "target_values": candidate.target_values,
        },
        "review_version": facts.review_version,
        "root_fingerprint": facts.root_fingerprint,
        "client_version": facts.client_version,
        "order_version": facts.order_version,
        "source_event_identity": source.source_event_identity,
        "source_fingerprint": source.source_fingerprint,
    }).value
    return HcmResubmissionPreview(
        candidate.review_identity,
        candidate.case_no,
        candidate.source_field,
        candidate.target_fields,
        facts.review_version,
        facts.root_fingerprint,
        fingerprint,
    )


def _validate_versions(request: ApplyHcmResubmission, facts: HcmResubmissionFacts) -> None:
    if request.expected_review_version != facts.review_version:
        raise HcmResubmissionConflict("hcm_resubmission_review_stale")
    if request.expected_root_fingerprint != facts.root_fingerprint:
        raise HcmResubmissionConflict("hcm_resubmission_root_stale")


def _command_fingerprint(request: ApplyHcmResubmission) -> str:
    return fingerprint_payload({
        "review_identity": request.review_identity,
        "source_event_identity": request.source.source_event_identity,
        "source_fingerprint": request.source.source_fingerprint,
        "target_values": dict(sorted(request.source.target_values.items())),
        "expected_review_version": request.expected_review_version,
        "expected_root_fingerprint": request.expected_root_fingerprint,
        "preview_fingerprint": request.preview_fingerprint,
        "actor": request.actor,
        "reason": request.reason,
    }).value


def _verify_readback(
    values: Mapping[str, object],
    before: HcmResubmissionFacts,
    candidate: HcmFieldCorrectionCandidate,
) -> None:
    expected_client = before.client_version + (
        1 if any(key.startswith("clients.") for key in candidate.target_values) else 0
    )
    expected_order = before.order_version + (
        1 if any(key.startswith("orders.") for key in candidate.target_values) else 0
    )
    try:
        actual_client = int(values["client_hcm_correction_version"])
        actual_order = int(values["order_version"])
    except (KeyError, TypeError, ValueError):
        raise HcmResubmissionConflict("hcm_resubmission_readback_mismatch") from None
    if actual_client != expected_client:
        raise HcmResubmissionConflict("hcm_resubmission_readback_mismatch")
    if actual_order != expected_order:
        raise HcmResubmissionConflict("hcm_resubmission_readback_mismatch")


def _client_command(
    facts: HcmResubmissionFacts,
    candidate: HcmFieldCorrectionCandidate,
    request: ApplyHcmResubmission,
) -> ClientHcmCorrectionCommand | None:
    client_values = {
        key.split(".", 1)[1]: value
        for key, value in candidate.target_values.items()
        if key.startswith("clients.")
    }
    if not client_values:
        return None
    return ClientHcmCorrectionCommand(
        client_id=facts.client_id,
        case_no=facts.case_no,
        expected_client_version=facts.client_version,
        review_identity=facts.review_identity,
        source_event_identity=request.source.source_event_identity,
        field_path=candidate.source_field,
        values=client_values,
        idempotency_key=request.idempotency_key,
        actor=request.actor,
        reason=request.reason,
        correlation_id=request.correlation_id,
        source_fingerprint=request.source.source_fingerprint,
    )


__all__ = [
    "ApplyHcmResubmission",
    "HcmResubmissionConflict",
    "HcmResubmissionPreview",
    "HcmResubmissionReceipt",
    "HcmResubmissionSource",
    "HcmResubmissionWorkflow",
    "hcm_resubmission_source_event_identity",
]
