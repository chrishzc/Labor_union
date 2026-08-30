from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.imports import reprocess_finance_import_batch as reprocess_cli
from subsystems.finance_import import reprocessing


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, *, database: str, server: str, schema_rows: list[dict[str, Any]]):
        self.database = database
        self.server = server
        self.schema_rows = schema_rows
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, _params: object = None) -> None:
        self.statement = statement

    def fetchone(self) -> dict[str, str]:
        assert "SELECT DATABASE()" in self.statement
        return {"database_name": self.database, "server_name": self.server}

    def fetchall(self) -> list[dict[str, Any]]:
        assert "information_schema.columns" in self.statement
        return self.schema_rows


class _Connection:
    def __init__(self, cursor: _Cursor):
        self.cursor_value = cursor
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


def _schema_rows() -> list[dict[str, Any]]:
    return [
        {
            "table_name": table,
            "ordinal_position": 1,
            "column_name": "id",
            "column_type": "bigint",
            "is_nullable": "NO",
            "column_default": None,
            "extra": "",
        }
        for table in reprocess_cli._REQUIRED_SCHEMA_TABLES
    ]


def test_legacy_service_is_removed_and_typed_diagnostic_rejects_apply():
    # The old top-level services package is absent; checking its path avoids
    # importlib raising ModuleNotFoundError while resolving a missing parent.
    assert not (ROOT / "services" / "finance_import_reprocessing.py").exists()
    with pytest.raises(ValueError, match="legacy_finance_import_reprocess_apply_retired"):
        reprocessing.reprocess_finance_import_batch(
            1,
            dry_run=False,
            connection_factory=lambda: pytest.fail(
                "retired apply must not open a connection"
            ),
        )


def test_legacy_cli_apply_is_rejected_before_calling_the_service(monkeypatch):
    monkeypatch.setattr(
        reprocess_cli,
        "reprocess_finance_import_batch",
        lambda *_args, **_kwargs: pytest.fail("legacy apply must not call a service"),
    )

    with pytest.raises(ValueError, match="legacy_finance_import_reprocess_apply_retired"):
        reprocess_cli.main(["--batch-id", "1", "--apply"])


def test_read_only_cli_requires_explicit_identity_before_calling_service(monkeypatch):
    monkeypatch.setattr(
        reprocess_cli,
        "reprocess_finance_import_batch",
        lambda *_args, **_kwargs: pytest.fail("identity guard must run first"),
    )

    with pytest.raises(ValueError, match="--target-database is required"):
        reprocess_cli.main(["--batch-id", "1"])


def test_read_only_connection_guard_binds_config_database_server_and_schema(monkeypatch):
    database = "finance_recovery_simulation"
    host = "mysql-test-host"
    server = "mysql-test-server"
    rows = _schema_rows()
    expected_fingerprint = reprocess_cli._schema_fingerprint(
        _Cursor(database=database, server=server, schema_rows=rows), database
    )
    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "database", database)
    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "host", host)
    connection = _Connection(
        _Cursor(database=database, server=server, schema_rows=rows)
    )

    factory = reprocess_cli._guarded_connection_factory(
        target_database=database,
        expected_host=host,
        expected_server=server,
        expected_schema_fingerprint=expected_fingerprint,
        connection_factory=lambda: connection,
    )

    assert factory() is connection
    assert connection.closed is False


@pytest.mark.parametrize(
    ("configured_database", "configured_host", "message"),
    [
        ("wrong_database", "mysql-test-host", "configured database"),
        ("finance_recovery_simulation", "wrong-host", "configured host"),
    ],
)
def test_read_only_connection_guard_rejects_config_drift_before_connect(
    monkeypatch,
    configured_database: str,
    configured_host: str,
    message: str,
):
    opened = False

    def connection_factory():
        nonlocal opened
        opened = True
        return pytest.fail("config drift must fail before connection")

    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "database", configured_database)
    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "host", configured_host)
    factory = reprocess_cli._guarded_connection_factory(
        target_database="finance_recovery_simulation",
        expected_host="mysql-test-host",
        expected_server="mysql-test-server",
        expected_schema_fingerprint="0" * 64,
        connection_factory=connection_factory,
    )

    with pytest.raises(RuntimeError, match=message):
        factory()

    assert opened is False


@pytest.mark.parametrize(
    ("connected_database", "connected_server", "fingerprint", "message"),
    [
        ("wrong_database", "mysql-test-server", None, "connected database"),
        ("finance_recovery_simulation", "wrong-server", None, "connected server"),
        ("finance_recovery_simulation", "mysql-test-server", "0" * 64, "schema fingerprint drift"),
    ],
)
def test_read_only_connection_guard_closes_on_identity_or_schema_drift(
    monkeypatch,
    connected_database: str,
    connected_server: str,
    fingerprint: str | None,
    message: str,
):
    database = "finance_recovery_simulation"
    host = "mysql-test-host"
    rows = _schema_rows()
    expected_fingerprint = fingerprint or reprocess_cli._schema_fingerprint(
        _Cursor(database=database, server="mysql-test-server", schema_rows=rows),
        database,
    )
    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "database", database)
    monkeypatch.setitem(reprocess_cli.DB_CONFIG, "host", host)
    connection = _Connection(
        _Cursor(
            database=connected_database,
            server=connected_server,
            schema_rows=rows,
        )
    )
    factory = reprocess_cli._guarded_connection_factory(
        target_database=database,
        expected_host=host,
        expected_server="mysql-test-server",
        expected_schema_fingerprint=expected_fingerprint,
        connection_factory=lambda: connection,
    )

    with pytest.raises(RuntimeError, match=message):
        factory()

    assert connection.closed is True
