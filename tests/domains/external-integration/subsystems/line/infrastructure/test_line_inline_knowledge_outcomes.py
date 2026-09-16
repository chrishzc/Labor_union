"""Execute the existing inline-outcome SQL against isolated in-memory tables.

The actual owner methods are compiled from repository source, without importing
connection factories or credential/provider composition. SQLite substitutes
placeholders and timestamp syntax; only its unique-key error is translated to
the MySQL duplicate-key shape. These are sequential SQL/readback regressions,
not MySQL isolation/locking, managed-UoW, HTTP, or provider acceptance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[6]
SOURCE = ROOT / "infrastructure/mysql/knowledge_retrieval_unit_of_work.py"


class DriverIntegrityError(Exception):
    """Local driver boundary: only args[0] is consumed by the owner method."""


def owner_methods():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == "KnowledgeRetrievalMySqlUnitOfWork")
    names = {"record_inline_outcome", "answer_receipt_catalog_revision"}
    methods = [node for node in owner.body if isinstance(node, ast.FunctionDef)
               and node.name in names]
    assert {node.name for node in methods} == names
    module = ast.Module(body=methods, type_ignores=[])
    namespace = {"IntegrityError": DriverIntegrityError,
                 "mysql_error_code": lambda error: error.args[0]}
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return type("InlineOutcomeOwner", (), {name: namespace[name] for name in names})


class SqlCursor:
    def __init__(self, connection):
        self.connection = connection
        self.raw = connection.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()

    def execute(self, sql, values=()):
        self.connection.statements.append(sql)
        if self.connection.error is not None:
            raise self.connection.error
        sql = sql.replace("%s", "?").replace("CURRENT_TIMESTAMP(6)", "CURRENT_TIMESTAMP")
        try:
            self.raw.execute(sql, values)
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise
            raise DriverIntegrityError(1062, "duplicate fixture key") from error

    @property
    def lastrowid(self):
        return self.raw.lastrowid

    def fetchone(self):
        row = self.raw.fetchone()
        return None if row is None else dict(row)


class SqlConnection:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.statements = []
        self.error = None
        # Only input/observation roots exist. An accidental job or delivery write
        # fails rather than being swallowed by a catch-all mock.
        self.db.executescript("""
            CREATE TABLE knowledge_answer_requests (
                id INTEGER PRIMARY KEY, question TEXT NOT NULL,
                requester_line_user_id TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL,
                correlation_id TEXT NOT NULL, request_status TEXT NOT NULL,
                completed_at_utc TEXT);
            CREATE TABLE knowledge_answer_receipts (
                id INTEGER PRIMARY KEY, index_version INTEGER);
        """)

    def cursor(self):
        return SqlCursor(self)

    def requests(self):
        return tuple(tuple(row) for row in self.db.execute(
            "SELECT * FROM knowledge_answer_requests ORDER BY id"))


@pytest.fixture
def owner():
    connection = SqlConnection()
    value = owner_methods()()
    value._connection = connection
    try:
        yield value, connection
    finally:
        connection.db.close()


def command(**changes):
    values = dict(question="synthetic question", requester_line_user_id="test-actor-a",
                  idempotency_key=SimpleNamespace(value="test-inline-interaction"),
                  correlation_id=SimpleNamespace(value="test-inline-correlation"))
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("status", ["unsupported", "failed"])
def test_terminal_request_persists_once_and_exact_replay_reads_same_identity(owner, status):
    app, connection = owner
    request = command()
    first = app.record_inline_outcome(request, status)
    before = connection.requests()
    assert len(before) == 1
    assert before[0][1:6] == (request.question, request.requester_line_user_id,
                              request.idempotency_key.value, request.correlation_id.value, status)
    assert before[0][6] is not None
    assert app.record_inline_outcome(request, status) == first
    assert connection.requests() == before
    assert connection.db.execute("SELECT COUNT(*) FROM knowledge_answer_receipts").fetchone()[0] == 0
    assert all(sql.startswith(("INSERT INTO knowledge_answer_requests ",
                               "SELECT id,question,")) for sql in connection.statements)


@pytest.mark.parametrize("status", ["unsupported", "failed"])
@pytest.mark.parametrize("change", ["question", "actor", "correlation", "status"])
def test_same_identity_different_request_is_rejected_without_changing_original(owner, status, change):
    app, connection = owner
    app.record_inline_outcome(command(), status)
    before = connection.requests()
    changes = {
        "question": {"question": "different synthetic question"},
        "actor": {"requester_line_user_id": "test-actor-b"},
        "correlation": {"correlation_id": SimpleNamespace(value="different-correlation")},
        "status": {},
    }[change]
    requested_status = ("failed" if status == "unsupported" else "unsupported") if change == "status" else status
    with pytest.raises(RuntimeError, match="^knowledge_answer_idempotency_conflict$"):
        app.record_inline_outcome(command(**changes), requested_status)
    assert connection.requests() == before


@pytest.mark.parametrize("status", ["answered", "processing", ""])
def test_invalid_terminal_state_does_not_reach_storage(owner, status):
    app, connection = owner
    with pytest.raises(ValueError, match="^knowledge_inline_outcome_invalid$"):
        app.record_inline_outcome(command(), status)
    assert connection.statements == []
    assert connection.requests() == ()


def test_missing_actor_does_not_create_an_observation(owner):
    app, connection = owner
    with pytest.raises(ValueError, match="^knowledge_inline_answer_actor_required$"):
        app.record_inline_outcome(command(requester_line_user_id=""), "failed")
    assert connection.statements == []
    assert connection.requests() == ()


def test_non_duplicate_driver_failure_is_not_treated_as_replay(owner):
    app, connection = owner
    connection.error = DriverIntegrityError(1452, "synthetic foreign-key failure")
    with pytest.raises(DriverIntegrityError) as caught:
        app.record_inline_outcome(command(), "failed")
    assert caught.value is connection.error
    assert len(connection.statements) == 1
    assert connection.requests() == ()


def test_catalog_revision_is_read_from_exact_receipt_without_writes(owner):
    app, connection = owner
    connection.db.executemany("INSERT INTO knowledge_answer_receipts VALUES (?,?)", [(7, 12), (8, 33)])
    before = connection.db.total_changes
    assert app.answer_receipt_catalog_revision(7) == 12
    assert app.answer_receipt_catalog_revision(8) == 33
    assert app.answer_receipt_catalog_revision(999) is None
    assert connection.db.total_changes == before
    assert all(sql.startswith("SELECT index_version ") for sql in connection.statements)


def test_missing_persisted_catalog_revision_is_not_invented(owner):
    app, connection = owner
    connection.db.execute("INSERT INTO knowledge_answer_receipts VALUES (7,NULL)")
    assert app.answer_receipt_catalog_revision(7) is None
