"""
File: test_historical_order_review_remediation_workflow.py
Description: 驗證歷史訂單更正的去敏 Query、零寫入 Preview、stale 與 replay。
"""

from __future__ import annotations

from dataclasses import dataclass

from openpyxl import Workbook
import pytest

from domains.orders.historical_review_remediation import (
    HistoricalReviewContext,
    HistoricalReviewCorrectionSource,
    HistoricalReviewDisposition,
    build_correction_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.historical_review_remediation_workflow import (
    ApplyHistoricalReviewRemediation,
    HistoricalReviewRemediationReceipt,
    HistoricalReviewRemediationWorkflow,
    HistoricalReviewRemediationWorkflowError,
)


def _context(remediation_version: int = 0) -> HistoricalReviewContext:
    return HistoricalReviewContext(
        "historical-order-review:1", "historical-orders:event:1", "a" * 64,
        "CA****01", "CASE-1", 11, "current_conflict", None, 0, remediation_version, (),
    )


def test_clean_source_builds_corrected_disposition() -> None:
    source = HistoricalReviewCorrectionSource("b" * 64, "source:2", "c" * 64, "CASE-1", "王小明", (), object())
    candidate = build_correction_candidate(_context(), source)
    assert candidate.disposition is HistoricalReviewDisposition.CORRECTED_SOURCE_ADOPTED
    assert candidate.successor_required is False
    assert candidate.blockers == ()


def test_source_issue_builds_successor_disposition() -> None:
    source = HistoricalReviewCorrectionSource("b" * 64, "source:2", "c" * 64, "CASE-1", "王小明", ("historical_status_invalid",), object())
    candidate = build_correction_candidate(_context(), source)
    assert candidate.disposition is HistoricalReviewDisposition.SUPERSEDED_BY_REPLACEMENT_REVIEW
    assert candidate.successor_required is True
    assert candidate.blockers == ("historical_status_invalid",)


def test_preview_is_zero_write_and_requires_one_row(tmp_path) -> None:
    path = _workbook(tmp_path / "clean.xlsx", 1)
    repository = _Repository(_context())
    workflow = HistoricalReviewRemediationWorkflow(repository, _uow)
    preview = _preview(workflow, path)
    assert preview.candidate.disposition.value == "corrected_source_adopted"
    assert repository.persisted == 0
    assert repository.lock_modes == [True, True]


def test_preview_fingerprint_materializes_actor_capability(tmp_path) -> None:
    path = _workbook(tmp_path / "clean.xlsx", 1)
    workflow = HistoricalReviewRemediationWorkflow(_Repository(_context()), _uow)

    owner = workflow.preview(
        "historical-order-review:1",
        path,
        ExpectedVersion(0),
        ExpectedVersion(0),
        ActorContext("operator", ("orders.historical_review.remediate",)),
        "電話確認",
        ("call:1",),
        CorrelationId("corr-preview-owner"),
    )
    unscoped = workflow.preview(
        "historical-order-review:1",
        path,
        ExpectedVersion(0),
        ExpectedVersion(0),
        ActorContext("operator"),
        "電話確認",
        ("call:1",),
        CorrelationId("corr-preview-unscoped"),
    )

    assert owner.fingerprint != unscoped.fingerprint


def test_apply_rejects_stale_preview_without_persisting(tmp_path) -> None:
    path = _workbook(tmp_path / "clean.xlsx", 1)
    repository = _Repository(_context())
    workflow = HistoricalReviewRemediationWorkflow(repository, _uow)
    command = ApplyHistoricalReviewRemediation(
        "historical-order-review:1", str(path), ExpectedVersion(0), ExpectedVersion(0), PreviewFingerprint("d" * 64),
        IdempotencyKey("remediation-key"), ActorContext("operator"), "電話確認", ("call:1",), CorrelationId("corr-apply"),
    )
    with pytest.raises(HistoricalReviewRemediationWorkflowError) as raised:
        workflow.apply(command)
    assert raised.value.error.code == "historical_order_remediation_preview_stale"
    assert repository.persisted == 0


def test_apply_replays_same_receipt(tmp_path) -> None:
    path = _workbook(tmp_path / "clean.xlsx", 1)
    repository = _Repository(_context())
    workflow = HistoricalReviewRemediationWorkflow(repository, _uow)
    preview = _preview(workflow, path)
    command = ApplyHistoricalReviewRemediation(
        "historical-order-review:1", str(path), ExpectedVersion(0), ExpectedVersion(0), preview.fingerprint,
        IdempotencyKey("remediation-key"), ActorContext("operator"), "電話確認", ("call:1",), CorrelationId("corr-apply"),
    )
    first = workflow.apply(command)
    second = workflow.apply(command)
    assert first.replayed is False
    assert second.replayed is True
    assert first.remediation_receipt_identity == second.remediation_receipt_identity
    assert repository.persisted == 1


def _workbook(path, status):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["case_no", "client_name", "status"])
    sheet.append(["CASE-1", "王小明", status])
    workbook.save(path)
    return str(path)


@dataclass
class _Uow:
    committed: bool = False
    rolled_back: bool = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _Repository:
    def __init__(self, context):
        self.context = context
        self.receipt = None
        self.persisted = 0
        self.lock_modes = []

    def load_context(self, identity, *, for_update):
        self.lock_modes.append(for_update)
        return self.context if identity == self.context.review_identity else None

    def find_receipt(self, key):
        return self.receipt

    def evaluate_source(self, context, source, *, for_update):
        self.lock_modes.append(for_update)
        del context
        return source

    def persist(self, command, context, candidate):
        self.persisted += 1
        self.receipt = (
            PreviewFingerprint(_command_fingerprint(command)),
            HistoricalReviewRemediationReceipt(context.review_identity, "receipt:1", candidate.disposition.value, None, candidate.source.workbook_digest, 1, command.preview_fingerprint, False),
        )
        return self.receipt[1]


def _uow():
    return _Uow()


def _preview(workflow, path):
    return workflow.preview(
        "historical-order-review:1",
        path,
        ExpectedVersion(0),
        ExpectedVersion(0),
        ActorContext("operator"),
        "電話確認",
        ("call:1",),
        CorrelationId("corr-preview"),
    )


def _command_fingerprint(command):
    from subsystems.orders.historical_review_remediation_workflow import (
        _source,
        historical_review_remediation_command_fingerprint,
    )

    return historical_review_remediation_command_fingerprint(
        command, _source(command.source_path)
    ).value
