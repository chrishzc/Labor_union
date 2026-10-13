"""
File: hcm_resubmission_workflow.py
Description: 提供 HCM 問題查詢及逐欄人工略過；工作簿修正命令已退役。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Protocol

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from domains.case_import.hcm_import_review import (
    HCM_SKIP_REJECT_REASON_PATH, hcm_field_skip_path,
    validate_hcm_field_skip, validate_missing_reject_reason_skip,
)


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
    unresolved_fields: tuple[str, ...] = ()


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
    source_field: str | None = None


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


    def find_receipt(self, idempotency_key: str, *, for_update: bool = False) -> tuple[str, HcmResubmissionReceipt] | None: ...


    def save_receipt(
        self,
        idempotency_key: str,
        command_fingerprint: str,
        preview_fingerprint: str,
        receipt: HcmResubmissionReceipt,
    ) -> None: ...

    def append_outbox(self, event_identity: str, review_identity: str) -> None: ...


def _skip_preview(facts: HcmReviewSkipFacts, source_field: str | None = None) -> HcmReviewSkipPreview:
    if source_field is None:
        validate_missing_reject_reason_skip(issue_codes=facts.issue_codes, reject_reason=facts.reject_reason,
                                           already_skipped=facts.already_skipped, is_current=facts.is_current)
    else:
        validate_hcm_field_skip(source_field=source_field, unresolved_fields=facts.unresolved_fields,
                                is_current=facts.is_current)
    fingerprint = fingerprint_payload({
        "operation": HCM_SKIP_REJECT_REASON_PATH if source_field is None else hcm_field_skip_path(source_field),
        "review_identity": facts.review_identity,
        "case_no": facts.case_no, "review_version": facts.review_version,
        "source_fingerprint": facts.source_fingerprint,
    }).value
    return HcmReviewSkipPreview(facts.review_identity, facts.case_no, source_field or "不符合原因",
                               facts.review_version, fingerprint)


class HcmResubmissionConflict(ValueError):
    pass


class HcmResubmissionWorkflow:
    def __init__(self, repository: HcmResubmissionRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_review(self, review_identity: str):
        return self._repository.query_review(review_identity)

    def preview_skip(self, review_identity: str, source_field: str | None = None) -> HcmReviewSkipPreview:
        return _skip_preview(self._repository.load_skip_facts(review_identity, for_update=False), source_field)

    def apply_skip(self, request: ApplyHcmReviewSkip) -> HcmResubmissionReceipt:
        command_fingerprint = fingerprint_payload({
            "operation": HCM_SKIP_REJECT_REASON_PATH if request.source_field is None else hcm_field_skip_path(request.source_field),
            "review_identity": request.review_identity,
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
                preview = _skip_preview(facts, request.source_field)
            except ValueError as error:
                raise HcmResubmissionConflict("hcm_review_skip_stale") from error
            if preview.preview_fingerprint != request.preview_fingerprint:
                raise HcmResubmissionConflict("hcm_review_skip_stale")
            event_identity = self._repository.apply_skip(facts, request)
            receipt = HcmResubmissionReceipt(event_identity, facts.review_identity, facts.case_no,
                                            (HCM_SKIP_REJECT_REASON_PATH if request.source_field is None else hcm_field_skip_path(request.source_field),),
                                            facts.review_version + 1, False)
            self._repository.save_receipt(request.idempotency_key, command_fingerprint,
                                          preview.preview_fingerprint, receipt)
            self._repository.append_outbox(event_identity, facts.review_identity)
            unit_of_work.commit()
        return receipt

    def query_current_reviews(self, *, limit: int, before_id: int | None):
        return self._repository.query_current_reviews(limit=limit, before_id=before_id)


__all__ = [
    "ApplyHcmReviewSkip",
    "HcmReviewSkipFacts",
    "HcmReviewSkipPreview",
    "HcmResubmissionConflict",
    "HcmResubmissionReceipt",
    "HcmResubmissionWorkflow",
]
