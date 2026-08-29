"""
File: test_historical_operational_baseline_workflow.py
Description: 驗證歷史作業基準 workflow 的唯讀、fresh lock、重播與交易邊界。
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from domains.orders.historical_operational_baseline import (
    HistoricalBaselineEvidenceMode,
    HistoricalOperationalBaselineFacts,
    HistoricalOperationalBaselineRequest,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.historical_operational_baseline_workflow import (
    ApplyHistoricalOperationalBaseline,
    HistoricalOperationalBaselinePersisted,
    HistoricalOperationalBaselineReceipt,
    HistoricalOperationalBaselineWorkflow,
    HistoricalOperationalBaselineWorkflowError,
    StoredHistoricalOperationalBaselineReceipt,
    historical_operational_baseline_command_fingerprint,
)


def _fp(value: str = "a") -> PreviewFingerprint:
    return PreviewFingerprint(value * 64)


def _identity() -> HistoricalOrderIdentity:
    return HistoricalOrderIdentity("order:CASE-1", "CASE-1")


def _facts(version: int = 4, binding: PreviewFingerprint | None = None):
    return HistoricalOperationalBaselineFacts(
        _identity(),
        HistoricalOrderProvenanceIdentity("historical-adoption:CASE-1", 2),
        version,
        binding or _fp(),
    )


def _request(version: int = 4, binding: PreviewFingerprint | None = None, reason: str = "人工核對"):
    return HistoricalOperationalBaselineRequest(
        _identity(),
        8,
        version,
        binding or _fp(),
        HistoricalBaselineEvidenceMode.RETAINED,
        reason,
        "evidence:CASE-1",
    )


def _command(preview_fingerprint: PreviewFingerprint, *, key: str = "hob:case-1", reason: str = "人工核對"):
    return ApplyHistoricalOperationalBaseline(
        _identity(),
        8,
        ExpectedVersion(4),
        _fp(),
        HistoricalBaselineEvidenceMode.RETAINED,
        reason,
        "evidence:CASE-1",
        preview_fingerprint,
        IdempotencyKey(key),
        ActorContext("admin_user_id:7", ("orders.historical_baseline",)),
        CorrelationId("correlation:hob-1"),
    )


class _Uow:
    def __init__(self):
        self.events: list[str] = []

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.events.append("exit")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


class _Repository:
    def __init__(self, facts=None):
        self.facts = facts or _facts()
        self.calls: list[tuple[str, bool | None]] = []
        self.receipt: StoredHistoricalOperationalBaselineReceipt | None = None
        self.appended = []
        self.saved = []

    def load_facts(self, identity, *, for_update):
        self.calls.append(("load_facts", for_update))
        return self.facts if identity == self.facts.identity else None

    def find_receipt(self, key, *, for_update):
        self.calls.append(("find_receipt", for_update))
        return self.receipt

    def append_baseline(self, command, candidate, command_fingerprint):
        self.calls.append(("append_baseline", None))
        self.appended.append((command, candidate, command_fingerprint))
        return HistoricalOperationalBaselinePersisted(
            "baseline-event:CASE-1:1", "baseline-receipt:CASE-1:1", candidate.current_orders_version
        )

    def save_receipt(self, key, stored):
        self.calls.append(("save_receipt", None))
        self.saved.append((key, stored))
        self.receipt = stored


class _Outbox:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)
        return len(self.intents)


def _workflow(repository=None, outbox=None, uow=None):
    repository = repository or _Repository()
    outbox = outbox or _Outbox()
    uow = uow or _Uow()
    return HistoricalOperationalBaselineWorkflow(repository, outbox, lambda: uow), repository, outbox, uow


def test_query_and_preview_are_read_only_unlocked_reads() -> None:
    workflow, repository, outbox, uow = _workflow()

    query = workflow.query(_identity(), CorrelationId("correlation:query"))
    preview = workflow.preview(
        _request(), ActorContext("admin_user_id:7", ("orders.historical_baseline",)), CorrelationId("correlation:preview")
    )

    assert query.facts == _facts()
    assert preview.candidate.selected_step == 8
    assert repository.calls == [("load_facts", False), ("load_facts", False)]
    assert repository.appended == []
    assert repository.saved == []
    assert outbox.intents == []
    assert uow.events == []


def test_apply_fresh_locks_appends_receipt_and_outbox_then_commits() -> None:
    workflow, repository, outbox, uow = _workflow()
    actor = ActorContext("admin_user_id:7", ("orders.historical_baseline",))
    preview = workflow.preview(_request(), actor, CorrelationId("correlation:preview"))
    command = _command(preview.fingerprint)

    receipt = workflow.apply(command)

    assert receipt.replayed is False
    assert receipt.selected_step == 8
    assert receipt.resulting_orders_version == 4
    assert repository.calls[-4:] == [
        ("find_receipt", True),
        ("load_facts", True),
        ("append_baseline", None),
        ("save_receipt", None),
    ]
    assert uow.events == ["enter", "commit", "exit"]
    assert len(outbox.intents) == 1
    intent = outbox.intents[0]
    assert intent.intent_type == "historical_operational_baseline_confirmed"
    assert json.loads(intent.payload_json)["selected_step"] == 8
    assert json.dumps(json.loads(intent.payload_json), ensure_ascii=False, sort_keys=True, separators=(",", ":")) == intent.payload_json


def test_same_key_same_command_replays_without_reappend() -> None:
    workflow, repository, outbox, uow = _workflow()
    actor = ActorContext("admin_user_id:7", ("orders.historical_baseline",))
    preview = workflow.preview(_request(), actor, CorrelationId("correlation:preview"))
    command = _command(preview.fingerprint)
    first = workflow.apply(command)
    repository.calls.clear()
    uow.events.clear()

    replay = workflow.apply(command)

    assert replay == replace(first, replayed=True)
    assert repository.calls == [("find_receipt", True)]
    assert len(repository.appended) == 1
    assert len(outbox.intents) == 1
    assert uow.events == ["enter", "commit", "exit"]


def test_same_key_different_payload_is_typed_mismatch_and_zero_write() -> None:
    workflow, repository, outbox, uow = _workflow()
    actor = ActorContext("admin_user_id:7", ("orders.historical_baseline",))
    preview = workflow.preview(_request(), actor, CorrelationId("correlation:preview"))
    workflow.apply(_command(preview.fingerprint))
    repository.calls.clear()
    uow.events.clear()

    with pytest.raises(HistoricalOperationalBaselineWorkflowError) as raised:
        workflow.apply(_command(preview.fingerprint, reason="另一個人工理由"))

    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH
    assert raised.value.error.code == "historical_operational_baseline_idempotency_mismatch"
    assert repository.calls == [("find_receipt", True)]
    assert len(repository.appended) == 1
    assert len(outbox.intents) == 1
    assert uow.events == ["enter", "rollback", "exit"]


def test_fresh_version_change_rejects_stale_apply_and_rolls_back() -> None:
    repository = _Repository()
    workflow, repository, outbox, uow = _workflow(repository=repository)
    actor = ActorContext("admin_user_id:7", ("orders.historical_baseline",))
    preview = workflow.preview(_request(), actor, CorrelationId("correlation:preview"))
    command = _command(preview.fingerprint)
    repository.facts = _facts(version=5)

    with pytest.raises(HistoricalOperationalBaselineWorkflowError) as raised:
        workflow.apply(command)

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "historical_baseline_stale"
    assert repository.appended == []
    assert outbox.intents == []
    assert uow.events == ["enter", "rollback", "exit"]


def test_preview_fingerprint_mismatch_is_zero_write_conflict() -> None:
    workflow, repository, outbox, uow = _workflow()
    command = _command(_fp("f"))

    with pytest.raises(HistoricalOperationalBaselineWorkflowError) as raised:
        workflow.apply(command)

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "historical_operational_baseline_preview_stale"
    assert repository.appended == []
    assert outbox.intents == []
    assert uow.events == ["enter", "rollback", "exit"]


def test_outbox_failure_rolls_back_event_and_receipt() -> None:
    class FailingOutbox(_Outbox):
        def append(self, intent):
            raise RuntimeError("queue unavailable")

    workflow, repository, outbox, uow = _workflow(outbox=FailingOutbox())
    actor = ActorContext("admin_user_id:7", ("orders.historical_baseline",))
    preview = workflow.preview(_request(), actor, CorrelationId("correlation:preview"))

    with pytest.raises(HistoricalOperationalBaselineWorkflowError) as raised:
        workflow.apply(_command(preview.fingerprint))

    assert raised.value.error.category is ErrorCategory.INTERNAL
    assert raised.value.error.code == "historical_operational_baseline_transaction_failed"
    assert len(repository.appended) == 1
    assert len(repository.saved) == 1
    assert uow.events == ["enter", "rollback", "exit"]


def test_command_fingerprint_includes_actor_and_canonical_payload() -> None:
    command = _command(_fp())
    other_actor = replace(command, actor=ActorContext("admin_user_id:8", ("orders.historical_baseline",)))

    assert historical_operational_baseline_command_fingerprint(command) != historical_operational_baseline_command_fingerprint(other_actor)
