"""
File: test_hcm_resubmission_workflow.py
Description: 驗證 HCM 單欄修正 Apply 的鎖定、重播與 outbox 邊界。
"""

from __future__ import annotations

import pytest

from domains.case_import.hcm_resubmission import HcmResubmissionFacts
from domains.clients.hcm_correction import ClientHcmCorrectionCommand
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
            "hcm-review:one", "HCM-FIELD-001", "服務方式", "HCM-001", 2, 3, "hcm-source:prior", 4,
            "b" * 64,
        )
        self.receipts = {}
        self.applied = []
        self.outbox = []
        self.calls = []
        self.readback_values = {
            "client_hcm_correction_version": 1,
            "order_version": 0,
        }

    def load_facts(self, review_identity, *, for_update):
        assert review_identity == self.facts.review_identity
        return self.facts

    def find_receipt(self, idempotency_key):
        return self.receipts.get(idempotency_key)

    def apply_field_correction(self, candidate, source, **kwargs):
        self.calls.append("apply")
        self.applied.append((candidate, source, kwargs))
        return "correction-event:one"

    def save_receipt(self, idempotency_key, command_fingerprint, preview_fingerprint, receipt):
        self.calls.append("save_receipt")
        self.receipts[idempotency_key] = (command_fingerprint, receipt)

    def append_outbox(self, event_identity, occurrence_identity):
        self.calls.append("append_outbox")
        self.outbox.append((event_identity, occurrence_identity))

    def readback(self, case_no):
        assert case_no == self.facts.case_no
        self.calls.append("readback")
        return self.readback_values


class _UnitOfWork:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self.rollback()
        return False

    def commit(self):
        self.calls.append("commit")
        self.commits += 1

    def rollback(self):
        self.calls.append("rollback")
        self.rollbacks += 1


def _source() -> HcmResubmissionSource:
    return HcmResubmissionSource(
        {"服務方式": "週休二日", "姓名": "不應採納"},
        {},
        {"clients.service_type": "週休二日"},
        "hcm-resubmit-source:one",
        "a" * 64,
    )


def _request(workflow, source=None, **overrides):
    source = source or _source()
    preview = workflow.preview("hcm-review:one", source)
    values = {
        "review_identity": "hcm-review:one",
        "source": source,
        "expected_review_version": preview.review_version,
        "expected_root_fingerprint": preview.root_fingerprint,
        "preview_fingerprint": preview.preview_fingerprint,
        "idempotency_key": "hcm-resubmit-key",
        "actor": "admin",
        "reason": "補齊服務方式",
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return ApplyHcmResubmission(**values)


def test_apply_writes_only_candidate_targets_then_committed_outbox() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, lambda: _UnitOfWork(repository.calls))

    receipt = workflow.apply(_request(workflow))

    assert receipt.replayed is False
    assert repository.applied[0][0].target_values == {"clients.service_type": "週休二日"}
    assert repository.outbox == [("correction-event:one", "hcm-review:one")]
    assert isinstance(repository.applied[0][2]["client_command"], ClientHcmCorrectionCommand)
    assert repository.applied[0][2]["client_command"].values == {"service_type": "週休二日"}
    assert repository.calls == ["apply", "save_receipt", "append_outbox", "readback", "commit"]


def test_same_key_replays_and_different_payload_conflicts() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, lambda: _UnitOfWork(repository.calls))
    request = _request(workflow)

    assert workflow.apply(request).replayed is False
    assert workflow.apply(request).replayed is True
    with pytest.raises(HcmResubmissionConflict, match="idempotency_conflict"):
        workflow.apply(_request(workflow, reason="不同理由"))


def test_apply_rejects_stale_root_before_any_write() -> None:
    repository = _Repository()
    workflow = HcmResubmissionWorkflow(repository, lambda: _UnitOfWork(repository.calls))

    with pytest.raises(HcmResubmissionConflict, match="root_stale"):
        workflow.apply(_request(workflow, expected_root_fingerprint="c" * 64))
    assert repository.applied == []
    assert repository.outbox == []


def test_readback_mismatch_rolls_back_before_commit() -> None:
    repository = _Repository()
    repository.readback_values["client_hcm_correction_version"] = 99
    workflow = HcmResubmissionWorkflow(repository, lambda: _UnitOfWork(repository.calls))

    with pytest.raises(HcmResubmissionConflict, match="readback_mismatch"):
        workflow.apply(_request(workflow))

    assert repository.calls == ["apply", "save_receipt", "append_outbox", "readback", "rollback"]


def test_same_workbook_has_one_source_event_per_prior_warning() -> None:
    digest = "a" * 64

    assert hcm_resubmission_source_event_identity("hcm-review:one", digest) != (
        hcm_resubmission_source_event_identity("hcm-review:two", digest)
    )
