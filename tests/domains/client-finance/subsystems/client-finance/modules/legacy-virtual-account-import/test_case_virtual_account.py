"""Single-case writer oracles; SQL persistence uses an isolated in-memory DB.

SQLite executes the adapter's DML and emulates its named replacement procedure.
This does not claim to verify MySQL advisory or row-lock scheduling.
"""

from contextlib import contextmanager
import json
from types import SimpleNamespace
import sqlite3
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_registry_writer, get_access_control_connection_factory
from api.dependencies.legacy_virtual_account_import import get_case_virtual_account_application
from api.routes.case_virtual_account import router
from infrastructure.mysql.legacy_virtual_account_repository import MySqlLegacyVirtualAccountRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.client_finance.case_virtual_account import CaseVirtualAccountApplication, CaseVirtualAccountError
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account, resolve_client_virtual_account

CASE, OTHER = "114000001", "114000002"
OLD, NEW = "99781699114001", "99781699114999"
PATH = f"/api/v1/admin/client-finance/cases/{CASE}/virtual-account"


class _Cursor:
    def __init__(self, raw, statements):
        self.raw, self.statements = raw, statements

    def execute(self, sql, args=()):
        self.statements.append(sql)
        if sql.startswith("CALL `lu_nas_replace_case_account_v1`"):
            case, expected, account, digest, actor = args
            current = [row['id'] for row in self.raw.execute(
                'SELECT id FROM client_legacy_virtual_accounts WHERE case_no=? ORDER BY id', (case,))]
            assert current == json.loads(expected)
            self.raw.execute('DELETE FROM client_legacy_virtual_accounts WHERE case_no=?', (case,))
            self.raw.execute('INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (?,?,?,0,?)', (case, account, digest, actor))
            return
        self.raw.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), args)

    def nextset(self):
        return None

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()


class _Connection:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.row_factory = lambda cursor, row: dict(zip([column[0] for column in cursor.description], row))
        self.statements = []
        self.raw.executescript("""
            CREATE TABLE orders(case_no TEXT PRIMARY KEY);
            CREATE TABLE client_legacy_virtual_accounts(
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_no TEXT, virtual_account TEXT,
                source_content_digest TEXT, source_row INTEGER, created_by TEXT,
                UNIQUE(case_no,virtual_account));
            CREATE TABLE admin_command_receipts(
                command_family TEXT, idempotency_key TEXT, request_fingerprint TEXT,
                preview_fingerprint TEXT, actor TEXT, reason TEXT, result_snapshot TEXT,
                UNIQUE(command_family,idempotency_key));
            INSERT INTO orders VALUES ('114000001'),('114000002');
        """)

    @contextmanager
    def cursor(self):
        cursor = self.raw.cursor()
        try:
            yield _Cursor(cursor, self.statements)
        finally:
            cursor.close()

    def begin(self):
        self.raw.execute("BEGIN")

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


@pytest.fixture
def setup():
    connection = _Connection()
    repo = MySqlLegacyVirtualAccountRepository(connection)
    repo.acquire_lock = Mock(return_value=True)
    repo.release_lock = Mock()
    application = CaseVirtualAccountApplication(repo, lambda: MySqlUnitOfWork(connection))
    yield application, repo, connection
    connection.raw.close()


def _seed(connection, case_no, account):
    connection.raw.execute(
        "INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (?,?,?,2,'importer')",
        (case_no, account, "a" * 64),
    )
    connection.commit()


def _apply(application, state, key="edit-1", actor="admin", account=NEW):
    return application.apply(CASE, account, state.mapping_ids, key, actor)


@pytest.mark.parametrize("old_accounts", [(), (OLD,), (OLD, "99781699114888")])
def test_replaces_only_this_case_and_consumers_read_new_account(setup, old_accounts):
    application, repo, connection = setup
    for account in old_accounts:
        _seed(connection, CASE, account)
    _seed(connection, OTHER, "99781699114002")
    before = connection.raw.total_changes
    assert application.query(CASE).built_in_virtual_account == OLD
    state = application.query(CASE)
    assert connection.raw.total_changes == before  # Query is zero-write.
    receipt = _apply(application, state)
    assert receipt.before == tuple(sorted(old_accounts))
    assert application.query(CASE).imported_virtual_accounts == (NEW,)
    assert application.query(CASE).built_in_virtual_account == OLD
    assert application.query(OTHER).imported_virtual_accounts == ("99781699114002",)
    with connection.cursor() as cursor:
        assert resolve_case_virtual_account(cursor, CASE)["virtual_account"] == NEW
        assert resolve_client_virtual_account(cursor, NEW)["case_no"] == CASE
    stored = repo.load_case_account_receipt("edit-1")
    assert stored["actor"] == "admin"
    assert json.loads(stored["result_snapshot"])["before"] == list(sorted(old_accounts))
    row = connection.raw.execute("SELECT reason FROM admin_command_receipts").fetchone()
    assert row["reason"] == "後台客戶名冊虛擬帳號更新"
    assert any("orders" in sql and "FOR UPDATE" in sql for sql in connection.statements)
    assert any("client_legacy_virtual_accounts" in sql and "FOR UPDATE" in sql for sql in connection.statements)
    repo.release_lock.assert_called_once_with("edit-1")


def test_replay_returns_original_receipt_without_overwriting_later_change(setup):
    application, _, connection = setup
    first = application.query(CASE)
    original = _apply(application, first)
    later = application.query(CASE)
    _apply(application, later, key="edit-2", account=OLD)
    assert _apply(application, first) == original
    assert application.query(CASE).imported_virtual_accounts == (OLD,)
    assert connection.raw.execute("SELECT COUNT(*) AS n FROM admin_command_receipts").fetchone()["n"] == 2


@pytest.mark.parametrize("change", [{"actor": "other"}, {"account": OLD}])
def test_idempotency_rejects_changed_actor_or_command(setup, change):
    application, _, _ = setup
    state = application.query(CASE)
    _apply(application, state)
    with pytest.raises(CaseVirtualAccountError, match="相同操作識別碼"):
        _apply(application, state, **change)
    assert application.query(CASE).imported_virtual_accounts == (NEW,)


def test_stale_including_same_values_with_new_mapping_ids_is_rejected(setup):
    application, _, connection = setup
    _seed(connection, CASE, OLD)
    state = application.query(CASE)
    newer = application.query(CASE)
    _apply(application, newer, key="other-command", account=OLD)
    with pytest.raises(CaseVirtualAccountError) as caught:
        _apply(application, state)
    assert caught.value.code == "case_virtual_account_stale"
    assert application.query(CASE).imported_virtual_accounts == (OLD,)


def test_other_case_claiming_account_after_query_is_rejected(setup):
    application, _, connection = setup
    state = application.query(CASE)
    _seed(connection, OTHER, NEW)
    with pytest.raises(CaseVirtualAccountError) as caught:
        _apply(application, state)
    assert caught.value.code == "case_virtual_account_in_use"
    assert application.query(CASE).imported_virtual_accounts == ()


def test_receipt_failure_rolls_back_the_replacement(setup):
    application, repo, connection = setup
    _seed(connection, CASE, OLD)
    state = application.query(CASE)
    connection.raw.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON admin_command_receipts BEGIN SELECT RAISE(ABORT,'receipt unavailable'); END")
    with pytest.raises(sqlite3.IntegrityError, match="receipt unavailable"):
        _apply(application, state)
    assert application.query(CASE).imported_virtual_accounts == (OLD,)
    assert repo.load_case_account_receipt("edit-1") is None
    repo.release_lock.assert_called_once()


@pytest.mark.parametrize("account", ["", "123", "99781699１２３４５６", "9978169911400X"])
def test_invalid_format_is_zero_write(setup, account):
    application, _, connection = setup
    before = connection.raw.total_changes
    with pytest.raises(ValueError):
        _apply(application, application.query(CASE), account=account)
    assert connection.raw.total_changes == before


def test_lock_timeout_and_missing_case_are_typed(setup):
    application, repo, _ = setup
    with pytest.raises(CaseVirtualAccountError) as caught:
        application.query("missing")
    assert caught.value.status == 404
    state = application.query(CASE)
    repo.acquire_lock.return_value = False
    with pytest.raises(CaseVirtualAccountError) as caught:
        _apply(application, state)
    assert caught.value.status == 503
    repo.release_lock.assert_not_called()
    assert repo._lock_name("manual") == repo._lock_name("workbook")


def test_http_routes_require_auth_and_return_typed_conflicts(setup, monkeypatch):
    application, _, connection = setup
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    app.dependency_overrides[get_access_control_connection_factory] = lambda: Mock(side_effect=AssertionError("No real DB in route test"))
    app.dependency_overrides[get_case_virtual_account_application] = lambda: application
    with TestClient(app) as client:
        assert client.get(PATH).status_code in (401, 403)
        app.dependency_overrides[require_registry_writer] = lambda: SimpleNamespace(username="admin")
        assert client.get(PATH).json()["data"]["imported_virtual_accounts"] == []
        invalid = client.post(PATH + "/apply", json={"virtual_account": "123", "expected_mapping_ids": []}, headers={"Idempotency-Key": "invalid"})
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["error"]["category"] == "validation"
        state = client.get(PATH).json()["data"]
        assert client.post(PATH + "/preview", json={"virtual_account": NEW}).status_code == 404
        _seed(connection, CASE, OLD)
        response = client.post(PATH + "/apply", json={"virtual_account": NEW, "expected_mapping_ids": state["mapping_ids"]}, headers={"Idempotency-Key": "http-1"})
        assert response.status_code == 409
        assert response.json()["detail"]["error"]["code"] == "case_virtual_account_stale"
        current = client.get(PATH).json()["data"]
        saved = client.post(PATH + "/apply", json={"virtual_account": NEW, "expected_mapping_ids": current["mapping_ids"]}, headers={"Idempotency-Key": "http-2"})
        assert saved.status_code == 200
        assert saved.json()["data"] == {"case_no": CASE, "before": [OLD], "virtual_account": NEW}
