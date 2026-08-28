"""
File: test_historical_operational_baseline_repository.py
Description: 驗證 B1 repository 的 exact identity、fresh lock、append-only 三表與零 hidden commit。
"""

from __future__ import annotations

import json

from domains.orders.historical_operational_baseline import (
    HistoricalBaselineEvidenceMode,
    HistoricalOperationalBaselineRequest,
    build_historical_operational_baseline_candidate,
)
from infrastructure.mysql.historical_operational_baseline_repository import (
    MySqlHistoricalOperationalBaselineOutbox,
    MySqlHistoricalOperationalBaselineRepository,
    canonical_historical_order_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import OutboxIntent
from subsystems.orders.historical_operational_baseline_workflow import (
    ApplyHistoricalOperationalBaseline,
    HistoricalOperationalBaselineReceipt,
    StoredHistoricalOperationalBaselineReceipt,
    historical_operational_baseline_command_fingerprint,
)


class _Cursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.rowcount = 1
        self.lastrowid = connection.next_lastrowid
        self._result = None

    def execute(self, sql, params) -> None:
        self.connection.executions.append((sql, params))
        self._result = (
            self.connection.results.pop(0)
            if self.connection.results
            else None
        )

    def fetchone(self):
        return self._result

    def close(self) -> None:
        pass


class _Connection:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.executions = []
        self.next_lastrowid = 91
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _facts_rows():
    return (
        {
            "case_no": "CASE-1",
            "lifecycle_version": 4,
            "source_event_identity": "historical-orders:book:row:2",
            "source_version": 17,
        },
        None,
    )


def _candidate_and_command():
    identity = canonical_historical_order_identity("CASE-1")
    connection = _Connection(*_facts_rows())
    repository = MySqlHistoricalOperationalBaselineRepository(connection)
    facts = repository.load_facts(identity, for_update=False)
    request = HistoricalOperationalBaselineRequest(
        identity,
        8,
        4,
        facts.current_owner_binding_fingerprint,
        HistoricalBaselineEvidenceMode.RETAINED,
        "人工核對歷史流程",
        "evidence:CASE-1",
    )
    candidate = build_historical_operational_baseline_candidate(facts, request)
    command = ApplyHistoricalOperationalBaseline(
        identity,
        8,
        ExpectedVersion(4),
        facts.current_owner_binding_fingerprint,
        HistoricalBaselineEvidenceMode.RETAINED,
        "人工核對歷史流程",
        "evidence:CASE-1",
        PreviewFingerprint("b" * 64),
        IdempotencyKey("hob:case-1"),
        ActorContext("admin:7", ("orders.historical_review.remediate",)),
        CorrelationId("correlation:hob-1"),
    )
    return candidate, command


def test_load_facts_uses_latest_historical_provenance_and_exact_lock() -> None:
    identity = canonical_historical_order_identity("CASE-1")
    connection = _Connection(*_facts_rows())
    repository = MySqlHistoricalOperationalBaselineRepository(connection)

    facts = repository.load_facts(identity, for_update=True)

    assert facts.identity == identity
    assert facts.historical_provenance.source_version == 17
    assert facts.current_orders_version == 4
    assert facts.prior_baseline_lineage is None
    assert all("FOR UPDATE" in sql for sql, _ in connection.executions)
    assert "adoption.outcome='adopted'" in connection.executions[0][0]
    assert connection.commits == connection.rollbacks == 0


def test_non_adopted_historical_receipt_is_not_baseline_eligible() -> None:
    identity = canonical_historical_order_identity("CASE-1")
    connection = _Connection(None)
    repository = MySqlHistoricalOperationalBaselineRepository(connection)

    assert repository.load_facts(identity, for_update=False) is None
    assert "adoption.outcome='adopted'" in connection.executions[0][0]
    assert len(connection.executions) == 1


def test_load_facts_rejects_noncanonical_order_identity() -> None:
    identity = canonical_historical_order_identity("CASE-1")
    wrong = type(identity)("order:CASE-OTHER", "CASE-1")
    connection = _Connection(_facts_rows()[0])
    repository = MySqlHistoricalOperationalBaselineRepository(connection)

    assert repository.load_facts(wrong, for_update=False) is None
    assert len(connection.executions) == 1


def test_append_receipt_and_outbox_target_only_b1_tables() -> None:
    candidate, command = _candidate_and_command()
    connection = _Connection()
    repository = MySqlHistoricalOperationalBaselineRepository(connection)
    command_fingerprint = historical_operational_baseline_command_fingerprint(
        command
    )

    persisted = repository.append_baseline(
        command,
        candidate,
        command_fingerprint,
    )
    receipt = HistoricalOperationalBaselineReceipt(
        command.identity,
        persisted.baseline_event_identity,
        persisted.receipt_identity,
        candidate.selected_step,
        candidate.current_orders_version,
        command.preview_fingerprint,
        command_fingerprint,
    )
    repository.save_receipt(
        command.idempotency_key,
        StoredHistoricalOperationalBaselineReceipt(command_fingerprint, receipt),
    )
    payload = json.dumps(
        {
            "baseline_event_identity": receipt.baseline_event_identity,
            "receipt_identity": receipt.receipt_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    outbox = MySqlHistoricalOperationalBaselineOutbox(connection)
    outbox.append(
        OutboxIntent(
            "orders.historical_operational_baseline",
            command.identity.order_identity,
            "historical_operational_baseline_confirmed",
            payload,
            command.idempotency_key.value,
        )
    )

    sql = "\n".join(statement for statement, _ in connection.executions)
    assert "INSERT INTO historical_order_operational_baseline_events" in sql
    assert "INSERT INTO historical_order_operational_baseline_receipts" in sql
    assert "INSERT INTO historical_order_operational_baseline_outbox" in sql
    assert "order_lifecycle_state_events" not in sql
    assert "historical_order_review_remediation" not in sql
    assert connection.commits == connection.rollbacks == 0


def test_receipt_replay_read_uses_explicit_event_identity_and_for_update() -> None:
    row = {
        "command_fingerprint": "c" * 64,
        "receipt_identity": "baseline-receipt:1",
        "preview_fingerprint": "d" * 64,
        "resulting_orders_version": 4,
        "baseline_event_identity": "baseline-event:1",
        "order_identity": "order:CASE-1",
        "case_no": "CASE-1",
        "selected_step": 8,
    }
    connection = _Connection(row)
    repository = MySqlHistoricalOperationalBaselineRepository(connection)

    stored = repository.find_receipt(
        IdempotencyKey("hob:case-1"),
        for_update=True,
    )

    assert stored.receipt.baseline_event_identity == "baseline-event:1"
    assert stored.receipt.replayed is False
    assert "FOR UPDATE" in connection.executions[0][0]
