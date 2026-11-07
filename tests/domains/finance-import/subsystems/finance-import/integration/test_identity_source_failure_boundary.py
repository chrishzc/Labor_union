"""Exercise ingestion error ownership without executing SQL, even on a fake cursor."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest
from pymysql.err import InterfaceError, OperationalError

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
    assert ingestion._IngestionProgress().mutations_started is False


def controlled_ingestion(monkeypatch, tmp_path, *, failure_at=None,
                         rollback_fails=False, close_fails=False,
                         commit_applied=False, audit_fails=False):
    """Run the real ingestion and audit boundaries; replace only SQL/normalizer ports."""
    workbook = tmp_path / "controlled.xlsx"
    workbook.write_bytes(b"synthetic controlled workbook")
    events = []
    pending = []
    durable = []
    attempts = []
    pending_attempts = []
    primary = OperationalError(2013, "synthetic source or commit acknowledgement loss")
    original_cause = RuntimeError("synthetic original driver cause")
    original_context = LookupError("synthetic earlier driver context")
    primary.__cause__ = original_cause
    primary.__context__ = original_context
    rollback_error = InterfaceError(0, "")
    close_error = InterfaceError(0, "")
    audit_error = OperationalError(2006, "synthetic audit unavailable")
    receipt = ingestion.FinanceWorkbookIngestionReceipt(
        "finance-import-batch:41", ingestion._source_digest(workbook), 1, 1, 0,
    )

    class ControlledConnection(Connection):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def commit(self):
            super().commit()
            events.append(f"{self.name}:commit")
            if self.name == "primary":
                if failure_at != "commit" or commit_applied:
                    durable.extend(pending)
                    pending.clear()
                if failure_at == "commit":
                    raise primary
            elif audit_fails == "commit":
                raise audit_error
            else:
                attempts.extend(pending_attempts)
                pending_attempts.clear()

        def rollback(self):
            super().rollback()
            events.append(f"{self.name}:rollback")
            if rollback_fails:
                raise rollback_error
            if self.name == "primary":
                pending.clear()
            else:
                pending_attempts.clear()

        def close(self):
            super().close()
            events.append(f"{self.name}:close")
            if close_fails:
                raise close_error

    connection = ControlledConnection("primary")
    audit_connection = ControlledConnection("audit")
    opened = []

    def factory():
        result = connection if not opened else audit_connection
        assert len(opened) < 2, "No automatic command or audit retry"
        opened.append(result)
        events.append(f"{result.name}:open")
        if result is audit_connection and audit_fails == "connect":
            raise audit_error
        return result

    def normalize(_path):
        events.append("normalize")
        return {"normalized_rows": []}

    def identity(_cursor):
        events.append("identity")
        if failure_at == "identity":
            raise primary
        return {}

    def stage(*_args, **_kwargs):
        events.append("stage")
        pending.append("business-and-batch-and-occurrence")
        if failure_at == "stage":
            raise primary
        return {"batch_id": 41}

    def save_receipt(*_args):
        events.append("receipt")
        pending.append("receipt")

    def save_success(*_args):
        events.append("success-attempt")
        pending.append("committed-attempt")

    def save_failed(_cursor, _key, _fingerprint, digest, phase, started, code):
        events.append("audit:save")
        assert connection.closes == 1, "Release original connection before independent audit"
        if audit_fails is True:
            raise audit_error
        attempt = ingestion.FinanceImportAttempt(
            "finance-import-attempt:41", digest, phase, code, "rolled_back",
            started, datetime(2026, 11, 7),
        )
        pending_attempts.append(attempt)
        return attempt

    monkeypatch.setattr(ingestion, "_find_replay_or_attempt", lambda *_: None)
    monkeypatch.setattr(ingestion, "_find_replay", lambda *_: None)
    monkeypatch.setattr(ingestion, "load_finance_identity_maps", identity)
    monkeypatch.setattr(ingestion, "stage_finance_rows", stage)
    monkeypatch.setattr(ingestion, "_persist_ingestion", lambda *_: receipt)
    monkeypatch.setattr(ingestion, "_save_receipt", save_receipt)
    monkeypatch.setattr(ingestion, "_save_success_attempt", save_success)
    monkeypatch.setattr(ingestion, "_save_or_load_failed_attempt", save_failed)

    def invoke(path=None, key=None, actor=None, **_kwargs):
        return ingestion.ingest_finance_workbook(
            str(path or workbook), key or IdempotencyKey("controlled-original-key"),
            actor or ActorContext("synthetic-admin"),
            connection_factory=factory, normalizer=normalize,
        )

    return SimpleNamespace(**locals())


def assert_preserved_primary(control):
    assert control.primary.__cause__ is control.original_cause
    assert control.primary.__suppress_context__ is True
    assert control.primary.__context__ is control.original_context
    seen = set()
    error = control.primary
    contexts = []
    while error is not None:
        assert id(error) not in seen, "Cleanup diagnostics must not form a context cycle"
        seen.add(id(error))
        contexts.append(error)
        assert error.__cause__ is not control.primary
        error = error.__context__
    assert control.original_context in contexts


def test_candidate_driver_disconnect_audits_after_failed_rollback_and_close(monkeypatch, tmp_path):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="identity",
                                   rollback_fails=True, close_fails=True)
    with pytest.raises(ingestion.FinanceImportAttemptError) as raised:
        control.invoke()
    assert raised.value.__cause__ is control.primary
    assert raised.value.attempt is control.attempts[0]
    assert raised.value.attempt.transaction_outcome == "rolled_back"
    assert raised.value.attempt.phase == "staging"
    assert raised.value.attempt.batch_identity is None
    assert control.events == ["primary:open", "normalize", "identity", "primary:rollback",
                              "primary:close", "audit:open", "audit:save", "audit:commit", "audit:close"]
    assert control.pending == control.durable == []
    assert_preserved_primary(control)


def test_postwrite_rollback_failure_remains_unresolved_without_failed_audit(monkeypatch, tmp_path):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="stage",
                                   rollback_fails=True, close_fails=True)
    with pytest.raises(OperationalError) as raised:
        control.invoke()
    assert raised.value is control.primary
    assert control.pending == ["business-and-batch-and-occurrence"]
    assert control.durable == control.attempts == []
    assert control.opened == [control.connection]
    assert_preserved_primary(control)


def test_postwrite_acknowledged_rollback_keeps_original_failure_audit(monkeypatch, tmp_path):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="stage")
    with pytest.raises(ingestion.FinanceImportAttemptError) as raised:
        control.invoke()
    assert raised.value.__cause__ is control.primary
    assert len(control.attempts) == 1
    assert control.pending == control.durable == []


@pytest.mark.parametrize("commit_applied", [False, True])
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_commit_ack_loss_never_creates_rolled_back_attempt(monkeypatch, tmp_path, commit_applied, rollback_fails):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="commit",
                                   commit_applied=commit_applied, rollback_fails=rollback_fails,
                                   close_fails=True)
    with pytest.raises(OperationalError) as raised:
        control.invoke()
    assert raised.value is control.primary
    assert control.attempts == [] and control.opened == [control.connection]
    assert control.connection.commits == control.connection.rollbacks == control.connection.closes == 1
    assert control.events.count("normalize") == control.events.count("stage") == 1
    assert bool(control.durable) is commit_applied
    assert_preserved_primary(control)


def test_audit_failure_and_its_failed_cleanup_preserve_original_driver_error(monkeypatch, tmp_path):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="identity",
                                   rollback_fails=True, close_fails=True, audit_fails=True)
    with pytest.raises(OperationalError) as raised:
        control.invoke()
    assert raised.value is control.primary
    assert control.attempts == []
    assert control.audit_connection.rollbacks == control.audit_connection.closes == 1
    assert control.audit_connection.commits == 0
    assert_preserved_primary(control)
    assert control.primary.__notes__ == [
        "Finance Import secondary failure (InterfaceError)",
        "Finance Import secondary failure (InterfaceError)",
        "Finance Import secondary failure (OperationalError)",
    ]


@pytest.mark.parametrize("audit_fails", ["connect", "commit"])
def test_unavailable_or_unresolved_audit_never_returns_a_fake_attempt(monkeypatch, tmp_path, audit_fails):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="identity", audit_fails=audit_fails)
    with pytest.raises(OperationalError) as raised:
        control.invoke()
    assert raised.value is control.primary
    assert control.attempts == []
    assert control.primary.__notes__ == ["Finance Import secondary failure (OperationalError)"]
    assert control.audit_connection.commits == (1 if audit_fails == "commit" else 0)
    assert_preserved_primary(control)


@pytest.mark.parametrize("failure_kind", ["attempt", "conflict"])
def test_existing_typed_replay_failure_survives_cleanup_failure(monkeypatch, tmp_path, failure_kind):
    control = controlled_ingestion(monkeypatch, tmp_path, rollback_fails=True, close_fails=True)
    attempt = ingestion.FinanceImportAttempt("finance-import-attempt:9", "a" * 64, "staging",
        "finance_import_processing_failed", "rolled_back", datetime(2026, 11, 7), datetime(2026, 11, 7))
    failure = ingestion.FinanceImportAttemptError(attempt) if failure_kind == "attempt" else ingestion._IdempotencyConflict()
    def replay_failure(*_args):
        raise failure
    monkeypatch.setattr(ingestion, "_find_replay_or_attempt", replay_failure)
    with pytest.raises((ingestion.FinanceImportAttemptError, ValueError)) as raised:
        control.invoke()
    assert (raised.value is failure) if failure_kind == "attempt" else (raised.value.__cause__ is failure)
    assert control.events == ["primary:open", "primary:rollback", "primary:close"]
    assert control.attempts == []


def test_committed_attempt_found_by_auditor_is_not_wrapped_as_failure(monkeypatch, tmp_path):
    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="identity")
    committed = ingestion.FinanceImportAttempt("finance-import-attempt:9", "a" * 64, "completed",
        None, "committed", datetime(2026, 11, 7), datetime(2026, 11, 7), "finance-import-batch:9")
    monkeypatch.setattr(ingestion, "_save_or_load_failed_attempt", lambda *_: committed)
    with pytest.raises(OperationalError) as raised:
        control.invoke()
    assert raised.value is control.primary
    assert control.events.count("normalize") == 1 and "stage" not in control.events
    assert control.attempts == []


def test_existing_committed_attempt_is_loaded_without_any_failure_insert(monkeypatch):
    committed = ingestion.FinanceImportAttempt("finance-import-attempt:9", "a" * 64, "completed",
        None, "committed", datetime(2026, 11, 7), datetime(2026, 11, 7), "finance-import-batch:9")
    monkeypatch.setattr(ingestion, "_find_attempt", lambda *_: committed)
    # object has no execute(): this tests the real helper's early return without
    # executing even a fake project SQL statement or changing the saved result.
    result = ingestion._save_or_load_failed_attempt(
        object(), IdempotencyKey("existing-committed"), "b" * 64, "a" * 64,
        "staging", datetime(2026, 11, 7), "finance_import_processing_failed",
    )
    assert result is committed


@pytest.mark.parametrize("replay", [False, True])
def test_confirmed_receipt_survives_close_failure_without_failed_attempt(monkeypatch, tmp_path, replay, caplog):
    control = controlled_ingestion(monkeypatch, tmp_path, close_fails=True)
    if replay:
        monkeypatch.setattr(ingestion, "_find_replay_or_attempt", lambda *_: replace(control.receipt, replayed=True))
    result = control.invoke()
    assert result.batch_identity == control.receipt.batch_identity
    assert result.replayed is replay
    assert control.attempts == [] and control.opened == [control.connection]
    assert control.connection.rollbacks == 0
    assert control.connection.commits == (0 if replay else 1)
    assert control.events.count("normalize") == control.events.count("stage") == (0 if replay else 1)
    assert "completed connection close failed (InterfaceError)" in caplog.text


@pytest.mark.parametrize("commit_applied", [False, True])
def test_http_commit_ack_failure_keeps_original_key_outcome_contract(monkeypatch, tmp_path, commit_applied):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_finance_import_ingestion_service, get_finance_import_query_service
    from api.routes.finance_import import router

    control = controlled_ingestion(monkeypatch, tmp_path, failure_at="commit", commit_applied=commit_applied)
    queried_keys = []
    class QueryPort:
        def ingestion_outcome(self, key):
            queried_keys.append(key)
            return {"status": "committed" if control.durable else "unknown",
                    "receipt": control.receipt if control.durable else None,
                    "source_content_digest": control.receipt.source_content_digest if control.durable else None,
                    "error_code": None, "phase": "completed" if control.durable else None}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="synthetic-admin")
    app.dependency_overrides[get_finance_import_ingestion_service] = lambda: control.invoke
    app.dependency_overrides[get_finance_import_query_service] = lambda: QueryPort()
    headers = {"Idempotency-Key": "original-http-key", "X-Correlation-ID": "synthetic-disconnect"}
    with TestClient(app) as client:
        response = client.post("/api/v1/finance-import/workbooks/ingest", headers=headers,
                               files={"workbook": ("synthetic.xlsx", b"synthetic controlled workbook")})
        assert response.status_code == 500
        assert response.json()["detail"]["error"]["code"] == "transaction_failed"
        assert response.json()["detail"]["error"]["retryable"] is False
        outcome = client.get("/api/v1/finance-import/workbooks/ingestion-outcome", headers=headers)
    assert outcome.status_code == 200
    assert outcome.json()["data"]["status"] == ("committed" if commit_applied else "unknown")
    assert bool(outcome.json()["data"]["receipt"]) is commit_applied
    assert queried_keys == ["original-http-key"]
    assert control.attempts == []
    assert control.events.count("normalize") == control.events.count("stage") == 1
