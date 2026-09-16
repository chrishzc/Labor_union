"""Exercise the real LIFF handler and Knowledge SQL with local boundaries.

AST loading avoids credential/provider composition and an installed MySQL driver;
no handler, persistence, transaction, or readback algorithm is reimplemented.
FastAPI/Pydantic run in-process. SQLite translates placeholders/timestamps and
its UNIQUE error only. This is not native MySQL isolation or LINE verification.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[6]


def load_definitions(path, namespace, names, *, methods=None):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=str(ROOT / path))
    selected = []
    found = set()
    for node in tree.body:
        name = getattr(node, "name", None)
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
        if name not in names:
            continue
        if methods and isinstance(node, ast.ClassDef) and name in methods:
            node.body = [part for part in node.body if getattr(part, "name", None) in methods[name]]
        selected.append(node)
        found.add(name)
    assert found == set(names), (path, set(names) - found)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    exec(compile(module, str(ROOT / path), "exec", dont_inherit=True), namespace)


class DriverIntegrityError(Exception):
    pass


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
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise DriverIntegrityError(1452, "synthetic storage failure")
        sql = sql.replace("%s", "?").replace("CURRENT_TIMESTAMP(6)", "CURRENT_TIMESTAMP")
        try:
            self.raw.execute(sql, values)
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise
            raise DriverIntegrityError(1062, "synthetic duplicate key") from error

    @property
    def lastrowid(self):
        return self.raw.lastrowid

    def fetchone(self):
        row = self.raw.fetchone()
        return None if row is None else dict(row)

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]


class SqlConnection:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.statements = []
        self.fail_on = None
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE knowledge_answer_requests (
                id INTEGER PRIMARY KEY, question TEXT NOT NULL,
                requester_line_user_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
                correlation_id TEXT NOT NULL, request_status TEXT NOT NULL,
                created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP, completed_at_utc TEXT);
            CREATE TABLE knowledge_answer_receipts (
                id INTEGER PRIMARY KEY, answer_request_id INTEGER NOT NULL UNIQUE
                REFERENCES knowledge_answer_requests(id), answer_text TEXT NOT NULL,
                index_version INTEGER NOT NULL, authoritative INTEGER NOT NULL,
                line_delivery_task_id INTEGER, answered_at_utc TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE knowledge_answer_sources (
                answer_receipt_id INTEGER NOT NULL REFERENCES knowledge_answer_receipts(id),
                source_identity TEXT NOT NULL, source_version INTEGER NOT NULL,
                safe_excerpt TEXT NOT NULL, citation_order INTEGER NOT NULL,
                UNIQUE(answer_receipt_id,citation_order));
        """)

    def cursor(self):
        return SqlCursor(self)

    def begin(self):
        self.db.execute("BEGIN")

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def snapshot(self):
        return tuple(tuple(tuple(row) for row in self.db.execute(f"SELECT * FROM {table} ORDER BY 1"))
                     for table in ("knowledge_answer_requests", "knowledge_answer_receipts", "knowledge_answer_sources"))


@pytest.fixture
def app(monkeypatch):
    module = ModuleType("_inline_knowledge_replay_owners")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    ns = module.__dict__
    ns.update(dataclass=dataclass, Any=Any, BaseModel=BaseModel, ConfigDict=ConfigDict,
              Field=Field, HTTPException=HTTPException, Depends=Depends,
              IntegrityError=DriverIntegrityError, mysql_error_code=lambda error: error.args[0],
              QA_SOURCE_PREFIX="line-common-qa:", _IDENTITY_MAXIMUM_LENGTH=191)
    load_definitions("shared_kernel/validation.py", ns, {"require_canonical_text"})
    load_definitions("shared_kernel/identities.py", ns, {"IdempotencyKey", "CorrelationId"})
    load_definitions("domains/knowledge_retrieval/knowledge.py", ns, {"KnowledgeAnswer", "KnowledgeCitation"})
    load_definitions("subsystems/knowledge_retrieval/contracts.py", ns, {"AskKnowledgeQuestionCommand"})
    load_definitions("api/dependencies/llm_configuration.py", ns,
                     {"LlmSemanticTestResult", "_qa_id_from_source", "_LEGACY_CATALOG_MARKER"})
    load_definitions("api/error_contracts.py", ns, {"typed_http_error"})
    # BaseResponse is a pure model; execute its complete original module.
    exec(compile((ROOT / "api/schemas/base.py").read_text(encoding="utf-8"), "api/schemas/base.py", "exec"), ns)
    load_definitions("infrastructure/mysql/unit_of_work.py", ns, {"MySqlUnitOfWork"})
    repo_methods = {"record_inline_answer", "_existing_inline_answer_receipt",
                    "_insert_citations", "get_answer_request", "_rows"}
    load_definitions("infrastructure/mysql/knowledge_retrieval_repository.py", ns,
                     {"MySqlKnowledgeRetrievalRepository", "_GET_ANSWER_REQUEST", "_GET_ANSWER_SOURCES"},
                     methods={"MySqlKnowledgeRetrievalRepository": repo_methods})
    # Keep every actual UoW method except the infrastructure-composing constructor.
    tree = ast.parse((ROOT / "infrastructure/mysql/knowledge_retrieval_unit_of_work.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "KnowledgeRetrievalMySqlUnitOfWork")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef) and n.name != "__init__"}
    load_definitions("infrastructure/mysql/knowledge_retrieval_unit_of_work.py", ns,
                     {"KnowledgeRetrievalMySqlUnitOfWork"}, methods={"KnowledgeRetrievalMySqlUnitOfWork": methods})
    connection = SqlConnection()
    def open_uow():
        unit = ns["KnowledgeRetrievalMySqlUnitOfWork"](connection)
        unit.knowledge = ns["MySqlKnowledgeRetrievalRepository"]()
        unit.knowledge._connection = connection
        return unit
    ns["open_knowledge_retrieval_unit_of_work"] = open_uow
    initial = ns["LlmSemanticTestResult"](
        outcome="answered", provider="synthetic", model="synthetic", index_version=7,
        qa_id="service-flow", source_identity="line-common-qa:service-flow", source_version=4,
        source_excerpt="synthetic governed excerpt", answer_text="synthetic governed answer", code=None)
    state = SimpleNamespace(result=initial, calls=0, verifier_calls=0)
    def query(question):
        state.calls += 1
        if isinstance(state.result, Exception):
            raise state.result
        return state.result
    invalid = type("InvalidLiffTokenError", (Exception,), {})
    def verify(token):
        state.verifier_calls += 1
        if token == "invalid-test-token":
            raise invalid()
        return SimpleNamespace(line_user_id=SimpleNamespace(value="actor-a" if token == "test-token-a" else "actor-b"))
    ns.update(LlmConfigurationApplication=Any,
              get_llm_configuration_application=lambda: SimpleNamespace(test_semantics=query),
              get_liff_token_verifier=lambda: SimpleNamespace(verify=verify),
              InvalidLiffTokenError=invalid,
              LiffVerificationUnavailableError=type("LiffVerificationUnavailableError", (Exception,), {}),
              public_router=APIRouter())
    route_tree = ast.parse((ROOT / "api/routes/line_service_help.py").read_text())
    names = {n.name for n in route_tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name not in {"service_help_page", "get_published_faqs", "FaqItem", "FaqListResponse"}}
    load_definitions("api/routes/line_service_help.py", ns, names)
    application = FastAPI()
    application.include_router(ns["public_router"])
    try:
        with TestClient(application) as client:
            yield SimpleNamespace(client=client, state=state, db=connection, ns=ns, open_uow=open_uow)
    finally:
        connection.db.close()


def request(app, **changes):
    body = dict(question="synthetic question", interaction_id="test-interaction-a", line_id_token="test-token-a")
    body.update(changes)
    return app.client.post("/ask", json=body)


@pytest.mark.parametrize("change", ["same", "index", "source-version", "answer", "unavailable"])
def test_answer_replay_uses_original_receipt_without_requery_or_write(app, change):
    first = request(app)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert (data["answer_receipt_id"], data["source_version"], data["index_version"]) == (1, 4, 7)
    before = app.db.snapshot()
    assert tuple(map(len, before)) == (1, 1, 1)
    if change == "index":
        app.state.result = replace(app.state.result, index_version=8)
    elif change == "source-version":
        app.state.result = replace(app.state.result, source_version=5)
    elif change == "answer":
        app.state.result = replace(app.state.result, answer_text="updated governed answer")
    elif change == "unavailable":
        app.state.result = RuntimeError("synthetic unavailable provider")
    app.db.statements.clear()
    replay = request(app)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert app.state.calls == 1
    assert app.state.verifier_calls == 2
    assert app.db.snapshot() == before
    assert app.db.statements and all(sql.startswith("SELECT ") for sql in app.db.statements)


def test_new_interaction_still_queries_current_catalog(app):
    first = request(app)
    app.state.result = replace(app.state.result, index_version=8, source_version=5, answer_text="updated governed answer")
    second = request(app, interaction_id="test-interaction-b")
    assert first.status_code == second.status_code == 200
    assert app.state.calls == 2
    assert second.json()["data"]["answer_receipt_id"] != first.json()["data"]["answer_receipt_id"]
    assert second.json()["data"]["index_version"] == 8
    assert second.json()["data"]["source_version"] == 5
    assert second.json()["data"]["answer_text"] == "updated governed answer"
    assert tuple(map(len, app.db.snapshot())) == (2, 2, 2)


@pytest.mark.parametrize("change", [{"question": "different question"}, {"line_id_token": "test-token-b"}])
def test_replay_binding_conflict_is_409_before_query_or_write(app, change):
    assert request(app).status_code == 200
    before = app.db.snapshot()
    app.db.statements.clear()
    result = request(app, **change)
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["error"]["code"] == "knowledge_answer_idempotency_conflict"
    assert "synthetic governed answer" not in result.text
    assert app.state.calls == 1
    assert app.db.snapshot() == before
    assert all(sql.startswith("SELECT ") for sql in app.db.statements)


@pytest.mark.parametrize("changes,status", [({"line_id_token": "invalid-test-token"}, 401), ({"line_id_token": ""}, 422)])
def test_identity_is_checked_before_replay_lookup(app, changes, status):
    assert request(app).status_code == 200
    app.db.statements.clear()
    result = request(app, **changes)
    assert result.status_code == status
    assert app.state.calls == 1
    assert app.db.statements == []


@pytest.mark.parametrize("original,status", [("unsupported", 200), ("provider_error", 503)])
def test_terminal_nonanswer_does_not_requery_into_a_different_result(app, original, status):
    answer = app.state.result
    app.state.result = replace(answer, outcome=original, answer_text=None, code="timeout")
    assert request(app).status_code == status
    before = app.db.snapshot()
    assert tuple(map(len, before)) == (1, 0, 0)
    app.state.result = answer
    app.db.statements.clear()
    replay = request(app)
    assert replay.status_code == status, replay.text
    if original == "unsupported":
        assert replay.json()["data"]["outcome"] == "unsupported"
        assert replay.json()["data"]["index_version"] is None  # not persisted; do not invent it
    assert app.state.calls == 1
    assert app.db.snapshot() == before
    assert all(sql.startswith("SELECT ") for sql in app.db.statements)


def test_lookup_failure_does_not_call_provider_or_claim_a_new_answer(app):
    assert request(app).status_code == 200
    before = app.db.snapshot()
    app.db.fail_on = "SELECT "
    result = request(app)
    assert result.status_code == 503
    assert app.state.calls == 1
    assert app.db.snapshot() == before
    assert "synthetic storage failure" not in result.text


def test_incomplete_answer_receipt_does_not_requery_or_look_successful(app):
    assert request(app).status_code == 200
    app.db.db.execute("DELETE FROM knowledge_answer_sources")
    before = app.db.snapshot()
    result = request(app)
    assert result.status_code == 503
    assert app.state.calls == 1
    assert app.db.snapshot() == before


def test_citation_write_failure_rolls_back_request_and_receipt(app):
    app.db.fail_on = "INSERT INTO knowledge_answer_sources "
    result = request(app)
    assert result.status_code == 503
    assert app.db.snapshot() == ((), (), ())


def test_anonymous_request_does_not_read_or_persist_actor_history(app):
    result = request(app, interaction_id="", line_id_token="")
    assert result.status_code == 200
    assert result.json()["data"]["answer_receipt_id"] is None
    assert app.state.calls == 1 and app.state.verifier_calls == 0
    assert app.db.statements == []
