"""
File: test_hcm_resubmission_workflow.py
Description: 驗證 HCM 單欄修正 Apply 的鎖定、重播與 outbox 邊界。
"""

from __future__ import annotations

import pytest

from domains.case_import.hcm_resubmission import HcmResubmissionFacts
from subsystems.case_import.hcm_resubmission_workflow import (
    ApplyHcmResubmission,
    HcmResubmissionConflict,
    HcmResubmissionSource,
    HcmResubmissionWorkflow,
    hcm_resubmission_source_event_identity,
)


class _Repository:
    def __init__(self) -> None:
        self.facts = HcmResubmissionFacts(
            "import-warning:one", 1, "HCM-FIELD-001", "身分資格", "HCM-001", 2, 3, "hcm-source:prior", 4,
            "b" * 64,
        )
        self.receipts = {}
        self.applied = []
        self.outbox = []

    def load_facts(self, occurrence_identity, *, for_update):
        assert occurrence_identity == self.facts.occurrence_identity
        return self.facts

    def find_receipt(self, idempotency_key):
        return self.receipts.get(idempotency_key)

    def apply_field_correction(self, candidate, source, **kwargs):
        self.applied.append((candidate, source, kwargs))
        return "correction-event:one"

    def save_receipt(self, idempotency_key, command_fingerprint, preview_fingerprint, receipt):
        self.receipts[idempotency_key] = (command_fingerprint, receipt)

    def append_outbox(self, event_identity, occurrence_identity):
        self.outbox.append((event_identity, occurrence_identity))


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self):
        return None

    def rollback(self):
        return None


def _source() -> HcmResubmissionSource:
    return HcmResubmissionSource(
        {"身分資格": "一般市民", "姓名": "不應採納"},
        {},
        {"clients.identity_status": "一般市民"},
        "hcm-resubmit-source:one",
        "a" * 64,
    )


def _request(workflow, source=None, **overrides):
    source = source or _source()
    preview = workflow.preview("import-warning:one", source)
    values = {
        "occurrence_identity": "import-warning:one",
        "source": source,
        "expected_occurrence_version": preview.occurrence_version,
        "expected_root_fingerprint": preview.root_fingerprint,
        "preview_fingerprint": preview.preview_fingerprint,
        "idempotency_key": "hcm-resubmit-key",
        "actor": "admin",
        "reason": "補齊身分資格",
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return ApplyHcmResubmission(**values)


def test_apply_writes_only_candidate_targets_then_committed_outbox() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, _UnitOfWork)

    receipt = workflow.apply(_request(workflow))

    assert receipt.replayed is False
    assert repository.applied[0][0].target_values == {"clients.identity_status": "一般市民"}
    assert repository.outbox == [("correction-event:one", "import-warning:one")]


def test_same_key_replays_and_different_payload_conflicts() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, _UnitOfWork)
    request = _request(workflow)

    assert workflow.apply(request).replayed is False
    assert workflow.apply(request).replayed is True
    with pytest.raises(HcmResubmissionConflict, match="idempotency_conflict"):
        workflow.apply(_request(workflow, reason="不同理由"))


def test_apply_rejects_stale_root_before_any_write() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, _UnitOfWork)

    with pytest.raises(HcmResubmissionConflict, match="root_stale"):
        workflow.apply(_request(workflow, expected_root_fingerprint="c" * 64))
    assert repository.applied == []
    assert repository.outbox == []


def test_same_workbook_has_one_source_event_per_prior_warning() -> None:
    digest = "a" * 64

    assert hcm_resubmission_source_event_identity("import-warning:one", digest) != (
        hcm_resubmission_source_event_identity("import-warning:two", digest)
    )
