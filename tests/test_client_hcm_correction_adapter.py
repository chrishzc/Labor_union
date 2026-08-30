"""Unit checks for Client owner adapter replay, stale, readback and UoW rules."""

from __future__ import annotations

import pytest

from domains.clients.hcm_correction import ClientHcmCorrectionCommand
from infrastructure.mysql.client_hcm_correction_adapter import MySqlClientHcmCorrectionAdapter


class _Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.rowcount = 1
        self.lastrowid = 9
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Connection:
    def __init__(self, rows=()):
        self.cursor_value = _Cursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _command(**changes):
    values = {
        "client_id": 3, "case_no": "CASE-3", "expected_client_version": 4,
        "review_identity": "review-3", "source_event_identity": "source-3",
        "field_path": "服務方式", "values": {"service_type": "週休一日"},
        "idempotency_key": "key-3", "actor": "admin", "reason": "修正",
        "correlation_id": "corr-3", "source_fingerprint": "a" * 64,
    }
    values.update(changes)
    return ClientHcmCorrectionCommand(**values)


def test_apply_updates_client_and_never_owns_connection_commit() -> None:
    connection = _Connection([
        None,
        {"case_no": "CASE-3", "client_hcm_correction_version": 4, "service_type": "連續服務"},
    ])
    receipt = MySqlClientHcmCorrectionAdapter(connection).apply_in_current_uow(_command())

    assert receipt.resulting_client_version == 5
    assert receipt.replayed is False
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert any("client_hcm_correction_version=client_hcm_correction_version+1" in sql for sql, _ in connection.cursor_value.executed)


def test_apply_rejects_stale_version_before_mutation() -> None:
    connection = _Connection([
        None,
        {"case_no": "CASE-3", "client_hcm_correction_version": 5, "service_type": "連續服務"},
    ])

    with pytest.raises(ValueError, match="client_hcm_correction_stale"):
        MySqlClientHcmCorrectionAdapter(connection).apply_in_current_uow(_command())

    assert len(connection.cursor_value.executed) == 2


def test_readback_returns_authoritative_client_version() -> None:
    connection = _Connection([
        {"id": 3, "case_no": "CASE-3", "client_hcm_correction_version": 5, "service_type": "週休一日"},
    ])

    assert MySqlClientHcmCorrectionAdapter(connection).readback(3)["client_hcm_correction_version"] == 5
