"""Behavior and safety oracles for operational-retention policy."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from chromadb.errors import NotFoundError

from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.runtime.operational_retention import (
    ManagedLogRetentionSource,
    MySqlKnowledgeRetentionSource,
    _aware_datetime,
    _row_candidate,
)
from subsystems.runtime_governance.operational_retention import (
    OperationalRetentionApplication,
    RetentionCandidate,
    RetentionDeleteResult,
    RetentionError,
    RetentionSourceSnapshot,
)


NOW = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)


class MemoryEvidence:
    def __init__(self) -> None:
        self.intents = {}
        self.receipts = {}

    def terminal_receipt(self, key):
        return self.receipts.get(key)

    def pending_intent(self, key):
        return self.intents.get(key) if key not in self.receipts else None

    def append_intent(self, intent):
        self.intents[intent.idempotency_key] = intent

    def append_terminal(self, receipt, actor_id):
        self.receipts[receipt.idempotency_key] = receipt

    def latest_by_source(self):
        return {}


class FakeSource:
    source_id = "observations"

    def __init__(self, candidates, *, current_bytes=100, high=200, low=100):
        self.items = {item.identity: item for item in candidates}
        self.current_bytes = current_bytes
        self.high = high
        self.low = low
        self.delete_calls = 0
        self.rotations = 0

    def snapshot(self, now, retention_days):
        cutoff = now - timedelta(days=retention_days)
        eligible = tuple(self.items.values())
        expired = tuple(item for item in eligible if item.occurred_at_utc <= cutoff)
        return RetentionSourceSnapshot(
            self.source_id,
            "技術觀測",
            "database",
            "eligible",
            self.current_bytes,
            len(eligible),
            len(expired),
            min((item.occurred_at_utc for item in eligible), default=None),
            sum(item.estimated_bytes for item in expired),
            self.high,
            self.low,
            "high" if self.high is not None and self.current_bytes > self.high else "normal",
        )

    def candidates(self, *, cutoff_at_utc, limit):
        return tuple(sorted(
            (item for item in self.items.values() if item.occurred_at_utc <= cutoff_at_utc),
            key=lambda item: (item.occurred_at_utc, item.identity),
        )[:limit])

    def delete(self, candidates):
        self.delete_calls += 1
        deleted = failed = size = 0
        for candidate in candidates:
            current = self.items.get(candidate.identity)
            if current is None:
                deleted += 1
                size += candidate.estimated_bytes
            elif current.version != candidate.version:
                failed += 1
            else:
                del self.items[candidate.identity]
                self.current_bytes = max(0, self.current_bytes - candidate.estimated_bytes)
                deleted += 1
                size += candidate.estimated_bytes
        return RetentionDeleteResult(deleted, size, failed, "stale" if failed else None)

    def rotate_oversized(self, now):
        self.rotations += 1
        return 0


class FakeCursor:
    def __init__(self, locked_row):
        self.locked_row = locked_row
        self.statements = []
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters):
        self.statements.append(statement)
        self.executions.append((statement, parameters))

    def fetchall(self):
        return (self.locked_row,) if self.locked_row is not None else ()


class FakeConnection:
    def __init__(self, locked_row):
        self.fake_cursor = FakeCursor(locked_row)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, *args):
        return self.fake_cursor

    def begin(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None


class FakeChroma:
    def __init__(self):
        self.deleted_versions = []

    def delete_index(self, index_version):
        self.deleted_versions.append(index_version)
        return True


def candidate(identity: str, age_days: int, size: int = 25):
    return RetentionCandidate(identity, f"v-{identity}", NOW - timedelta(days=age_days), size)


def test_day_30_is_eligible_but_day_29_is_preserved_and_preview_is_zero_write() -> None:
    source = FakeSource((candidate("day-30", 30), candidate("day-29", 29)))
    evidence = MemoryEvidence()
    app = OperationalRetentionApplication((source,), evidence, lambda: NOW)

    preview = app.preview(source_id=source.source_id, mode="expired", reason="到期清理")

    assert preview.candidate_count == 1
    assert preview.candidates[0].identity == "day-30"
    assert source.delete_calls == 0
    assert set(source.items) == {"day-30", "day-29"}

    receipt = app.apply(
        source_id=source.source_id,
        mode="expired",
        reason="到期清理",
        batch_size=preview.batch_size,
        previewed_at_utc=preview.previewed_at_utc,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key="retention:test:day30",
        correlation_id="retention:test:day30",
        actor_id="admin:7",
    )

    assert receipt.outcome == "completed"
    assert receipt.deleted_count == 1
    assert set(source.items) == {"day-29"}


def test_stale_preview_deletes_nothing() -> None:
    original = candidate("candidate", 31)
    source = FakeSource((original,))
    app = OperationalRetentionApplication((source,), MemoryEvidence(), lambda: NOW)
    preview = app.preview(source_id=source.source_id, mode="expired", reason="人工清理")
    source.items[original.identity] = replace(original, version="changed")

    with pytest.raises(RetentionError) as raised:
        app.apply(
            source_id=source.source_id,
            mode="expired",
            reason="人工清理",
            batch_size=preview.batch_size,
            previewed_at_utc=preview.previewed_at_utc,
            preview_fingerprint=preview.preview_fingerprint,
            idempotency_key="retention:test:stale",
            correlation_id="retention:test:stale",
            actor_id="admin:7",
        )

    assert raised.value.code == "retention_preview_stale"
    assert source.delete_calls == 0
    assert original.identity in source.items


def test_capacity_preview_selects_oldest_until_low_water_and_requires_configuration() -> None:
    source = FakeSource(
        (candidate("oldest", 20, 25), candidate("middle", 10, 25), candidate("newest", 1, 25)),
        current_bytes=140,
        high=120,
        low=90,
    )
    app = OperationalRetentionApplication((source,), MemoryEvidence(), lambda: NOW)

    preview = app.preview(source_id=source.source_id, mode="capacity", reason="容量壓力")

    assert [item.identity for item in preview.candidates] == ["oldest", "middle"]
    assert preview.estimated_reclaimable_bytes == 50

    unconfigured = FakeSource((candidate("old", 31),), high=None, low=None)
    blocked = OperationalRetentionApplication((unconfigured,), MemoryEvidence(), lambda: NOW)
    with pytest.raises(RetentionError) as raised:
        blocked.preview(source_id=unconfigured.source_id, mode="capacity", reason="容量壓力")
    assert raised.value.code == "retention_capacity_unconfigured"


def test_capacity_cleanup_reports_unrelieved_when_allowlist_candidates_are_insufficient() -> None:
    source = FakeSource(
        (candidate("only-eligible-record", 1, 25),),
        current_bytes=140,
        high=120,
        low=90,
    )
    app = OperationalRetentionApplication((source,), MemoryEvidence(), lambda: NOW)
    preview = app.preview(source_id=source.source_id, mode="capacity", reason="容量壓力")

    receipt = app.apply(
        source_id=source.source_id,
        mode="capacity",
        reason=preview.reason,
        batch_size=preview.batch_size,
        previewed_at_utc=preview.previewed_at_utc,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key="retention:test:capacity-unrelieved",
        correlation_id="retention:test:capacity-unrelieved",
        actor_id="admin:7",
    )

    assert receipt.outcome == "capacity_unrelieved"
    assert receipt.deleted_count == 1
    assert source.current_bytes == 115


def test_automatic_capacity_cleanup_records_unrelieved_when_no_candidate_exists() -> None:
    source = FakeSource((), current_bytes=140, high=120, low=90)
    app = OperationalRetentionApplication((source,), MemoryEvidence(), lambda: NOW)

    receipts = app.run_automatic()

    assert len(receipts) == 1
    assert receipts[0].outcome == "capacity_unrelieved"
    assert receipts[0].candidate_count == 0


def test_mysql_reconciliation_conflict_is_counted_and_string_datetime_is_utc(monkeypatch) -> None:
    source = MySqlKnowledgeRetentionSource(
        lambda: None,
        object(),
        high_water_bytes=None,
        low_water_bytes=None,
    )
    monkeypatch.setattr(source, "_delete_one", lambda item: False)

    result = source.delete((candidate("stale", 31),))

    assert result.deleted_count == 0
    assert result.failed_count == 1
    assert result.error_code == "retention_source_reconciliation_required"
    assert _aware_datetime("2026-09-09 08:00:00") == NOW


def test_mysql_source_deletes_request_graph_in_fk_order_and_checks_index_before_vector_delete() -> None:
    request_row = {
        "id": 7,
        "occurred_at_utc": NOW,
        "state": "answered",
        "receipt_version": 3,
        "source_version": 4,
        "job_version": 5,
    }
    request_connection = FakeConnection(request_row)
    source = MySqlKnowledgeRetentionSource(
        lambda: request_connection,
        FakeChroma(),
        high_water_bytes=None,
        low_water_bytes=None,
    )

    assert source._delete_one(_row_candidate("request", request_row, 25)) is True
    delete_statements = [
        statement for statement in request_connection.fake_cursor.statements
        if statement.startswith("DELETE")
    ]
    assert [
        "knowledge_answer_sources",
        "knowledge_answer_receipts",
        "knowledge_jobs",
        "knowledge_answer_requests",
    ] == [next(name for name in (
        "knowledge_answer_sources",
        "knowledge_answer_receipts",
        "knowledge_jobs",
        "knowledge_answer_requests",
    ) if name in statement) for statement in delete_statements]

    preview_row = {**request_row, "id": 9, "state": "stale"}
    changed_row = {**preview_row, "state": "failed"}
    index_connection = FakeConnection(changed_row)
    chroma = FakeChroma()
    index_source = MySqlKnowledgeRetentionSource(
        lambda: index_connection,
        chroma,
        high_water_bytes=None,
        low_water_bytes=None,
    )

    assert index_source._delete_one(_row_candidate("index", preview_row, 25)) is False
    assert chroma.deleted_versions == []
    assert index_connection.rollbacks == 1


def test_mysql_source_removes_index_metadata_when_vector_collection_is_already_missing() -> None:
    index_row = {
        "id": 9,
        "occurred_at_utc": NOW,
        "state": "stale",
        "receipt_version": 0,
        "source_version": 0,
        "job_version": 0,
    }

    class MissingOnDeleteClient:
        def __init__(self) -> None:
            self.delete_names = []

        def list_collections(self):
            return (SimpleNamespace(name="union_knowledge_v9"),)

        def delete_collection(self, name: str) -> None:
            self.delete_names.append(name)
            raise NotFoundError("collection was already deleted")

    connection = FakeConnection(index_row)
    client = MissingOnDeleteClient()
    gateway = ChromaKnowledgeGateway("ignored")
    gateway._client = lambda: client
    source = MySqlKnowledgeRetentionSource(
        lambda: connection,
        gateway,
        high_water_bytes=None,
        low_water_bytes=None,
    )

    assert source._delete_one(_row_candidate("index", index_row, 25)) is True
    assert client.delete_names == ["union_knowledge_v9"]
    assert (
        "DELETE FROM knowledge_indexes WHERE index_version=%s",
        ("9",),
    ) in connection.fake_cursor.executions
    assert connection.commits == 1


def test_same_idempotency_key_replays_terminal_receipt_without_second_delete() -> None:
    source = FakeSource((candidate("old", 31),))
    evidence = MemoryEvidence()
    app = OperationalRetentionApplication((source,), evidence, lambda: NOW)
    preview = app.preview(source_id=source.source_id, mode="expired", reason="到期清理")
    command = dict(
        source_id=source.source_id,
        mode="expired",
        reason="到期清理",
        batch_size=preview.batch_size,
        previewed_at_utc=preview.previewed_at_utc,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key="retention:test:replay",
        correlation_id="retention:test:replay",
        actor_id="admin:7",
    )

    first = app.apply(**command)
    replay = app.apply(**command)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.deleted_count == 1
    assert source.delete_calls == 1


def test_managed_log_source_only_deletes_closed_old_segments_and_rotates_oversized(tmp_path) -> None:
    old_closed = tmp_path / "worker.log.20260701.closed"
    young_closed = tmp_path / "api.log.20260908.closed"
    active = tmp_path / "api.log"
    business = tmp_path / "contract.pdf"
    old_closed.write_bytes(b"old")
    young_closed.write_bytes(b"young")
    active.write_bytes(b"oversized-active")
    business.write_bytes(b"must-stay")
    old_time = (NOW - timedelta(days=31)).timestamp()
    young_time = (NOW - timedelta(days=1)).timestamp()
    os.utime(old_closed, (old_time, old_time))
    os.utime(young_closed, (young_time, young_time))
    os.utime(active, (old_time, old_time))
    source = ManagedLogRetentionSource(
        (tmp_path,),
        high_water_bytes=1_000,
        low_water_bytes=500,
        segment_max_bytes=5,
    )

    candidates = source.candidates(cutoff_at_utc=NOW - timedelta(days=30), limit=50)
    assert len(candidates) == 1
    result = source.delete(candidates)

    assert result.deleted_count == 1
    assert not old_closed.exists()
    assert young_closed.exists()
    assert active.exists()
    assert business.exists()

    assert source.rotate_oversized(NOW) == 1
    assert not active.exists()
    assert any(path.name.startswith("api.log.") and path.name.endswith(".closed") for path in tmp_path.iterdir())
    assert business.exists()


def test_filesystem_root_is_rejected() -> None:
    with pytest.raises(ValueError):
        ManagedLogRetentionSource(
            (Path(Path.cwd().anchor),),
            high_water_bytes=None,
            low_water_bytes=None,
            segment_max_bytes=None,
        )
