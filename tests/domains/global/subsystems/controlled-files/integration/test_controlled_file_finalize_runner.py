"""Deterministic oracle for the bounded 1015 finalize runner."""

from datetime import datetime, timezone
from types import SimpleNamespace

from infrastructure.mysql import controlled_file_finalize_worker as runner_module
from subsystems.controlled_files.contracts import (
    ControlledFileStagingContent,
    ControlledFileStorageError,
)


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params):
        self.connection.queries += 1

    def fetchall(self):
        return [{"finalize_id": "cff_1234567890abcdef1234567890abcdef"}]


class _Connection:
    def __init__(self):
        self.queries = 0
        self.commits = 0
        self.closed = False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class _Repository:
    def claim_finalize_intent(self, _finalize_id, *, worker_id, observed_at):
        return SimpleNamespace(
            finalize_id="cff_1234567890abcdef1234567890abcdef",
            staging_id="cfs_1234567890abcdef1234567890abcdef",
            controlled_file_object_id="cf_1234567890abcdef1234567890abcdef",
            expected_sha256="a" * 64,
            state=SimpleNamespace(value="pending"),
            claim_token=f"{worker_id}:token",
            observed_sha256=None,
            observed_size_bytes=None,
            created_at=observed_at,
        )

    def acquire_finalize_lease(self, intent, *, worker_id, acquired_at):
        return SimpleNamespace(
            lease_id="cfl_1234567890abcdef1234567890abcdef",
            staging_id=intent.staging_id,
            holder=worker_id,
        )

    def mark_finalize_available(self, *_args, **_kwargs):
        return None

    def mark_finalize_reconciliation_required(self, *_args, **_kwargs):
        return None

    def release_finalize_lease(self, *_args, **_kwargs):
        return None


class _Storage:
    def finalize_staged(self, staging_id, *, expected_sha256):
        return ControlledFileStagingContent(
            staging_id, b"verified", expected_sha256, NOW,
        )


class _FailingStorage(_Storage):
    def finalize_staged(self, _staging_id, *, expected_sha256):
        raise ControlledFileStorageError(
            "controlled_file_staging_not_found", "missing", retryable=False
        )


def test_runner_claims_bounded_intent_and_commits_each_external_effect(monkeypatch):
    connections = []

    def connection_factory():
        connection = _Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(
        runner_module,
        "MySqlControlledFileReferenceFinalizeRepository",
        lambda _connection: _Repository(),
    )
    runner = runner_module.MySqlControlledFileFinalizeRunner(
        connection_factory,
        _Storage(),
        "controlled-file-finalize-test",
        lambda: NOW,
    )

    assert runner.run_once() == 1
    assert connections[0].queries == 1
    assert connections[0].closed is True
    assert connections[1].commits == 4
    assert connections[1].closed is True


def test_runner_exposes_reconciliation_outcome_without_reporting_success(monkeypatch):
    connections = []

    def connection_factory():
        connection = _Connection()
        connections.append(connection)
        return connection

    blocked = []

    class Repository(_Repository):
        def mark_finalize_reconciliation_required(self, *args, **kwargs):
            blocked.append(kwargs["error_code"])

    monkeypatch.setattr(
        runner_module,
        "MySqlControlledFileReferenceFinalizeRepository",
        lambda _connection: Repository(),
    )
    runner = runner_module.MySqlControlledFileFinalizeRunner(
        connection_factory,
        _FailingStorage(),
        "controlled-file-finalize-test",
        lambda: NOW,
    )

    assert runner.run_once() == 1
    assert blocked == ["controlled_file_staging_not_found"]
    assert connections[1].commits == 4
