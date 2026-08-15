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
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class HcmResubmissionSource:
    corrected_record: Mapping[str, object]
    validation_errors: Mapping[str, str]
    target_values: Mapping[str, object]
    source_event_identity: str
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class HcmResubmissionPreview:
    occurrence_identity: str
    case_no: str
    source_field: str
    target_fields: tuple[str, ...]
    occurrence_version: int
    root_fingerprint: str
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class ApplyHcmResubmission:
    occurrence_identity: str
    source: HcmResubmissionSource
    expected_occurrence_version: int
    expected_root_fingerprint: str
    preview_fingerprint: str
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class HcmResubmissionReceipt:
    event_identity: str
    occurrence_identity: str
    case_no: str
    target_fields: tuple[str, ...]
    replayed: bool


class HcmResubmissionRepository(Protocol):
    def load_facts(self, occurrence_identity: str, *, for_update: bool) -> HcmResubmissionFacts: ...

    def find_receipt(self, idempotency_key: str) -> tuple[str, HcmResubmissionReceipt] | None: ...

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

    def append_outbox(self, event_identity: str, occurrence_identity: str) -> None: ...


class HcmResubmissionConflict(ValueError):
    pass


class HcmResubmissionWorkflow:
    def __init__(self, repository: HcmResubmissionRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, occurrence_identity: str, source: HcmResubmissionSource) -> HcmResubmissionPreview:
        facts = self._repository.load_facts(occurrence_identity, for_update=False)
        candidate = _candidate(facts, source)
        return _preview(facts, candidate, source)

    def facts(self, occurrence_identity: str) -> HcmResubmissionFacts:
        """Read only the explicitly bound warning/root facts for owner input selection."""
        return self._repository.load_facts(occurrence_identity, for_update=False)

    def apply(self, request: ApplyHcmResubmission) -> HcmResubmissionReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise HcmResubmissionConflict("hcm_resubmission_idempotency_conflict")
                return replace(receipt, replayed=True)
            facts = self._repository.load_facts(request.occurrence_identity, for_update=True)
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
            )
            receipt = HcmResubmissionReceipt(
                event_identity,
                candidate.occurrence_identity,
                candidate.case_no,
                candidate.target_fields,
                False,
            )
            self._repository.save_receipt(
                request.idempotency_key,
                command_fingerprint,
                preview.preview_fingerprint,
                receipt,
            )
            self._repository.append_outbox(event_identity, candidate.occurrence_identity)
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
    occurrence_identity: str,
    workbook_fingerprint: str,
) -> str:
    """Scope a corrected workbook event to one prior warning occurrence."""
    if not occurrence_identity.strip() or len(workbook_fingerprint) != 64:
        raise ValueError("hcm_resubmission_source_identity_invalid")
    return "hcm-resubmission:" + hashlib.sha256(
        f"{occurrence_identity}:{workbook_fingerprint}".encode("utf-8")
    ).hexdigest()


def _preview(
    facts: HcmResubmissionFacts,
    candidate: HcmFieldCorrectionCandidate,
    source: HcmResubmissionSource,
) -> HcmResubmissionPreview:
    fingerprint = fingerprint_payload({
        "candidate": {
            "case_no": candidate.case_no,
            "occurrence_identity": candidate.occurrence_identity,
            "source_field": candidate.source_field,
            "target_fields": candidate.target_fields,
            "target_values": candidate.target_values,
        },
        "occurrence_version": facts.occurrence_version,
        "root_fingerprint": facts.root_fingerprint,
        "source_event_identity": source.source_event_identity,
        "source_fingerprint": source.source_fingerprint,
    }).value
    return HcmResubmissionPreview(
        candidate.occurrence_identity,
        candidate.case_no,
        candidate.source_field,
        candidate.target_fields,
        facts.occurrence_version,
        facts.root_fingerprint,
        fingerprint,
    )


def _validate_versions(request: ApplyHcmResubmission, facts: HcmResubmissionFacts) -> None:
    if request.expected_occurrence_version != facts.occurrence_version:
        raise HcmResubmissionConflict("hcm_resubmission_occurrence_stale")
    if request.expected_root_fingerprint != facts.root_fingerprint:
        raise HcmResubmissionConflict("hcm_resubmission_root_stale")


def _command_fingerprint(request: ApplyHcmResubmission) -> str:
    return fingerprint_payload({
        "occurrence_identity": request.occurrence_identity,
        "source_event_identity": request.source.source_event_identity,
        "source_fingerprint": request.source.source_fingerprint,
        "target_values": dict(sorted(request.source.target_values.items())),
        "expected_occurrence_version": request.expected_occurrence_version,
        "expected_root_fingerprint": request.expected_root_fingerprint,
        "preview_fingerprint": request.preview_fingerprint,
        "actor": request.actor,
        "reason": request.reason,
    }).value


__all__ = [
    "ApplyHcmResubmission",
    "HcmResubmissionConflict",
    "HcmResubmissionPreview",
    "HcmResubmissionReceipt",
    "HcmResubmissionSource",
    "HcmResubmissionWorkflow",
    "hcm_resubmission_source_event_identity",
]
