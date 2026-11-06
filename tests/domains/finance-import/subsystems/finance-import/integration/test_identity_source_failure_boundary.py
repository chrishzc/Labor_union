"""Exercise ingestion error ownership without executing SQL, even on a fake cursor."""

from contextlib import nullcontext
from datetime import datetime

import pytest

from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import import ingestion


class Connection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        # No execute/fetch methods: persistence must stay behind replaced ports.
        return nullcontext(object())

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_identity_source_failure_rolls_back_before_staging(monkeypatch, tmp_path):
    workbook = tmp_path / "statement.xlsx"
    workbook.write_bytes(b"synthetic source")
    connection = Connection()
    failure = ConnectionError("synthetic candidate source unavailable")
    events = []
    monkeypatch.setattr(ingestion, "_find_replay_or_attempt", lambda *_: None)
    monkeypatch.setattr(ingestion, "_find_replay", lambda *_: None)

    def unavailable(_cursor):
        raise failure

    def forbidden(*_args, **_kwargs):
        pytest.fail("source failure must not stage or persist financial facts")

    def record_failure(factory, key, fingerprint, digest, phase, started, code):
        assert connection.rollbacks == 1
        events.append((phase, code))
        return ingestion.FinanceImportAttempt(
            "finance-import-attempt:1", digest, phase, code, "rolled_back",
            started, datetime(2026, 11, 6),
        )

    monkeypatch.setattr(ingestion, "load_finance_identity_maps", unavailable)
    monkeypatch.setattr(ingestion, "stage_finance_rows", forbidden)
    monkeypatch.setattr(ingestion, "_persist_ingestion", forbidden)
    monkeypatch.setattr(ingestion, "_save_receipt", forbidden)
    monkeypatch.setattr(ingestion, "_save_success_attempt", forbidden)
    monkeypatch.setattr(ingestion, "_record_failed_attempt", record_failure)

    with pytest.raises(ingestion.FinanceImportAttemptError) as raised:
        ingestion.ingest_finance_workbook(
            str(workbook), IdempotencyKey("source-failure"), ActorContext("admin:1"),
            connection_factory=lambda: connection, normalizer=lambda _: {},
        )

    assert raised.value.__cause__ is failure
    assert raised.value.attempt.phase == "staging"
    assert raised.value.attempt.batch_identity is None
    assert events == [("staging", "finance_import_processing_failed")]
    assert (connection.commits, connection.rollbacks, connection.closes) == (0, 1, 1)


@pytest.mark.parametrize("candidates", [(), ({"staff_id": 1, "amount_due_ntd": 300},)])
def test_successful_identity_read_reaches_staging_unchanged(monkeypatch, candidates):
    connection = Connection()
    maps = {"staff_payout_candidates": candidates}
    normalized = {"normalized_rows": []}
    staged = {"batch_id": 1}
    receipt = ingestion.FinanceWorkbookIngestionReceipt("finance-import-batch:1", "a" * 64, 0, 0, 0)
    calls = []
    monkeypatch.setattr(ingestion, "_find_replay", lambda *_: None)
    monkeypatch.setattr(ingestion, "load_finance_identity_maps", lambda _: maps)

    def stage(_cursor, actual_normalized, actual_maps, *, business_only):
        assert actual_normalized is normalized
        assert actual_maps is maps
        assert business_only is True
        calls.append("stage")
        return staged

    monkeypatch.setattr(ingestion, "stage_finance_rows", stage)
    monkeypatch.setattr(ingestion, "_persist_ingestion", lambda *_: receipt)
    monkeypatch.setattr(ingestion, "_save_receipt", lambda *_: calls.append("receipt"))
    result = ingestion._ingest_or_replay(
        connection, normalized, "a" * 64, "b" * 64,
        IdempotencyKey("source-success"), ActorContext("admin:1"), ingestion._IngestionProgress(),
    )
    assert result is receipt
    assert calls == ["stage", "receipt"]
    assert (connection.commits, connection.rollbacks) == (0, 0)
