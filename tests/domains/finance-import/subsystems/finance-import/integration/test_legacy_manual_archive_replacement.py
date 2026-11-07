"""Historical archive compatibility and §19 replacement, without executing SQL.

The concrete command callback runs behind a typed command-store port. Its actual
MySQL lock/receipt ordering is checked statically, not declared database-tested.
"""
import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_statement_archive_application
import api.routes.finance_statement_workspace as routes
from domains.finance_import.statement_archive import validate_manual_statement
from infrastructure.mysql.finance_statement_archive_repository import MySqlStatementArchiveRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.finance_import.statement_archive import (
    ManualStatementReplacementRequired, StatementArchiveApplication, StatementCommandConflict,
    StatementCommandReceipt, StatementExportRow,
)


class NoSqlConnection:
    def __init__(self): self.events = []
    def cursor(self): raise AssertionError("Project SQL, including fake SQL, is forbidden")
    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")


class ArchiveCommandPort(MySqlStatementArchiveRepository):
    """Replace only SQL persistence; run the production callback and source check."""
    def __init__(self, connection):
        super().__init__(connection)
        self.previous = None
        self.writes = []
        self.historical = StatementExportRow("manual:7", "manual", "manual", (), tuple(validate_manual_statement(fields()).items()))

    def export_rows(self): return (self.historical,)

    def _command(self, command, key, actor, write):
        # This is a port oracle, not execution evidence for the MySQL method.
        digest = hashlib.sha256(json.dumps(command, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if self.previous:
            previous_digest, receipt = self.previous
            if previous_digest != digest: raise StatementCommandConflict("idempotency_conflict")
            return receipt
        receipt = write(None)  # Callback does not execute SQL or get a fake cursor.
        self.writes.append(receipt)
        self.previous = digest, receipt
        return receipt


def fields(): return {"交易日": "2026-11-06", "支出": 300, "備註": "synthetic"}


def historical_digest(fields_value, duplicate_of=None):
    command = {"operation": "manual", "fields": validate_manual_statement(fields_value), "duplicate_of": duplicate_of, "actor": "admin_user_id:1"}
    return hashlib.sha256(json.dumps(command, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def make_client():
    connection = NoSqlConnection()
    port = ArchiveCommandPort(connection)
    application = StatementArchiveApplication(port, lambda: MySqlUnitOfWork(connection))
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_statement_archive_application] = lambda: application
    return TestClient(app), connection, port


def test_archive_only_fresh_creation_is_typed_replacement_without_fact_or_command_write():
    client, connection, port = make_client()
    with client:
        response = client.post("/statements/manual", headers={"Idempotency-Key": "new"}, json={"fields": fields()})
    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert (error["category"], error["code"]) == ("domain_blocked", "case_manual_supplement_required")
    assert "案件帳務抽屜" in error["message"] and "手動補登" in error["message"]
    assert connection.events == ["begin", "rollback"]
    assert port.writes == [] and port.previous is None
    assert port.export_rows()[0].identity == "manual:7"


def test_exact_historical_command_replays_original_receipt_before_replacement_guard():
    client, connection, port = make_client()
    port.previous = historical_digest(fields()), StatementCommandReceipt("manual:7", 1, 0)
    with client:
        response = client.post("/statements/manual", headers={"Idempotency-Key": "old"}, json={"fields": fields()})
    assert response.status_code == 200
    assert response.json()["data"] == {"identity": "manual:7", "saved_count": 1, "excluded_count": 0}
    assert connection.events == ["begin", "commit"] and port.writes == []


def test_changed_historical_command_remains_conflict_without_new_write():
    client, connection, port = make_client()
    port.previous = historical_digest(fields()), StatementCommandReceipt("manual:7", 1, 0)
    with client:
        response = client.post("/statements/manual", headers={"Idempotency-Key": "old"}, json={"fields": {**fields(), "支出": 301}})
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["category"] == "conflict"
    assert connection.events == ["begin", "rollback"] and port.writes == []


@pytest.mark.parametrize("duplicate_of,status", [("manual:7", 200), ("manual:404", 409)])
def test_explicit_duplicate_still_checks_retained_historical_identity(duplicate_of, status):
    client, connection, port = make_client()
    with client:
        response = client.post("/statements/manual", headers={"Idempotency-Key": "duplicate"}, json={"fields": fields(), "duplicate_of": duplicate_of})
    assert response.status_code == status
    if status == 200:
        assert response.json()["data"] == {"identity": "manual:7", "saved_count": 0, "excluded_count": 1}
        assert connection.events == ["begin", "commit"]
    else:
        assert connection.events == ["begin", "rollback"] and port.writes == []


def test_historical_manual_export_is_preserved_and_read_only():
    client, connection, port = make_client()
    with client:
        response = client.get("/statements/export")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    values = list(workbook.active.values)
    assert values[1][1] == "2026-11-06" and values[1][6] == 300
    assert len(values) == 2 and connection.events == []


def test_concrete_archive_checks_original_receipt_before_replacement_callback_without_retiring_api():
    path = Path(__file__).resolve().parents[6] / "infrastructure/mysql/finance_statement_archive_repository.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    repository = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MySqlStatementArchiveRepository")
    command = next(node for node in repository.body if isinstance(node, ast.FunctionDef) and node.name == "_command")
    transaction = next(node for node in command.body if isinstance(node, ast.With))
    previous = next(node for node in transaction.body if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "previous")
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "write" for statement in previous.body for node in ast.walk(statement))
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "write" for statement in previous.orelse for node in ast.walk(statement))
    create = next(node for node in repository.body if isinstance(node, ast.FunctionDef) and node.name == "create_manual")
    assert not any(isinstance(node, ast.Constant) and isinstance(node.value, str) and "INSERT INTO finance_manual_statements" in node.value for node in ast.walk(create))
    # Source inspection confirms digest serialization remains byte-compatible.
    digest = next(node for node in ast.walk(command) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dumps")
    assert {arg.arg: ast.literal_eval(arg.value) for arg in digest.keywords} == {"sort_keys": True, "ensure_ascii": False}
    with pytest.raises(ManualStatementReplacementRequired):
        MySqlStatementArchiveRepository(NoSqlConnection())._confirm_manual_duplicate(None)
