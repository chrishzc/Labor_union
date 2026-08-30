"""Finance Import failures retain one safe, replayable attempt after rollback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from api.routes import finance_import as finance_import_route
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.finance_import import ingestion


class _Cursor:
    def __init__(self, rows: list[dict | None]) -> None:
        self.rows = rows
        self.inserted = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, _=None) -> None:
        if statement.startswith("INSERT INTO finance_import_ingestion_attempts"):
            self.inserted = True

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        if self.inserted:
            return _failed_attempt_row()
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None


def test_failed_normalization_writes_safe_attempt_and_exact_retry_replays_it(monkeypatch, tmp_path) -> None:
    workbook = tmp_path / "statement.xlsx"
    workbook.write_bytes(b"not-a-workbook")
    actor = ActorContext("test")
    source_digest = ingestion._source_digest(workbook)
    command_fingerprint = ingestion._command_fingerprint(source_digest, actor)
    failed_row = _failed_attempt_row(command_fingerprint)
    first_connection = _Connection(_Cursor([None, None]))
    audit_connection = _Connection(_Cursor([None, failed_row]))
    retry_connection = _Connection(_Cursor([None, failed_row]))
    connections = iter([first_connection, audit_connection, retry_connection])
    connection_factory = lambda: next(connections)
    key = IdempotencyKey("finance-import-attempt-test")

    with pytest.raises(ingestion.FinanceImportAttemptError) as first_error:
        ingestion.ingest_finance_workbook(
            str(workbook), key, actor, connection_factory=connection_factory,
            normalizer=_raise_invalid_workbook,
        )
    with pytest.raises(ingestion.FinanceImportAttemptError) as retry_error:
        ingestion.ingest_finance_workbook(
            str(workbook), key, actor, connection_factory=connection_factory,
            normalizer=_raise_invalid_workbook,
        )

    attempt = first_error.value.attempt
    assert first_connection.rolled_back is True
    assert audit_connection.committed is True
    assert attempt.transaction_outcome == "rolled_back"
    assert attempt.batch_identity is None
    assert attempt.error_code == "finance_import_validation_failed"
    assert retry_error.value.attempt == attempt


def test_ingestion_failure_http_error_contains_only_safe_attempt_fields() -> None:
    attempt = ingestion.FinanceImportAttempt(
        "finance-import-attempt:7", "a" * 64, "classification",
        "finance_import_processing_failed", "rolled_back",
        datetime(2026, 8, 9, 8), datetime(2026, 8, 9, 8), None,
    )

    with pytest.raises(Exception) as error:
        finance_import_route._raise_ingestion_attempt_error(
            ingestion.FinanceImportAttemptError(attempt), CorrelationId("attempt-error")
        )

    detail = error.value.detail
    assert detail["error"]["code"] == "finance_import_processing_failed"
    assert detail["attempt"]["batch_identity"] is None
    assert set(detail["attempt"]) == {
        "attempt_identity", "source_content_digest", "phase", "error_code",
        "transaction_outcome", "started_at", "completed_at", "batch_identity",
    }


def test_attempt_schema_is_append_only_and_excludes_bank_row_content() -> None:
    source = (Path(__file__).resolve().parents[1] / "db/schema_parts/152_finance_import_ingestion_attempts.sql").read_text(encoding="utf-8")

    assert "UNIQUE KEY uq_finance_import_attempt_command" in source
    assert "transaction_outcome ENUM('committed', 'rolled_back')" in source
    assert "cannot be updated" in source and "cannot be deleted" in source
    assert "counterparty_account" not in source
    assert "counterparty_name" not in source


def _raise_invalid_workbook(_):
    raise ValueError("untrusted workbook detail")


def _failed_attempt_row(command_fingerprint: str = "b" * 64) -> dict:
    return {
        "id": 7,
        "idempotency_key": "finance-import-attempt-test",
        "command_fingerprint": command_fingerprint,
        "source_content_digest": "a" * 64,
        "phase": "normalization",
        "error_code": "finance_import_validation_failed",
        "transaction_outcome": "rolled_back",
        "batch_id": None,
        "started_at": datetime(2026, 8, 9, 8),
        "completed_at": datetime(2026, 8, 9, 8),
    }
