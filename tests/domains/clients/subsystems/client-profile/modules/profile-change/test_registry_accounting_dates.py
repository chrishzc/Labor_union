"""Read-only registry dates: execute SELECTs, then validate the public response.

SQLite runs the portable SELECT/JOIN portion with a small DB-API adapter; this
is not a MySQL deployment or end-to-end accounting test.
"""
from datetime import date
import sqlite3

import pytest
from pydantic import ValidationError

from api.schemas.client_registry import ClientProfileChangeSet, ClientRegistryPageView
from infrastructure.mysql import client_registry_query_repository as repository_module
from subsystems.client_profile.registry_query import ClientRegistryQueryApplication


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()

    def execute(self, sql, parameters):
        assert sql.lstrip().upper().startswith("SELECT "), sql
        self.connection.statements.append((sql, parameters))
        self.cursor.execute(sql.replace("%s", "?"), parameters)

    def fetchall(self):
        return tuple(dict(row) for row in self.cursor.fetchall())


class _Connection:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("JSON_UNQUOTE", 1, lambda value: value)
        self.db.create_function("CONCAT_WS", -1, lambda separator, *values: separator.join(str(value) for value in values if value is not None))
        self.statements = []

    def cursor(self):
        return _Cursor(self)


@pytest.fixture
def connection(monkeypatch):
    connection = _Connection()
    connection.db.executescript("""
        CREATE TABLE orders (case_no TEXT, client_id INTEGER, service_days INTEGER,
            requires_cooking INTEGER, start_date DATE, status TEXT,
            staff_payment_due_date DATE, actual_end_date DATE);
        CREATE TABLE clients (id INTEGER, name TEXT, phone TEXT, city TEXT,
            address TEXT, identity_status TEXT);
        CREATE TABLE beclass_records (id INTEGER, bound_case_no TEXT, survey_details TEXT);
        CREATE TABLE beclass_record_correction_states (beclass_record_id INTEGER, effective_values_json TEXT);
        CREATE TABLE client_obligations (case_no TEXT, obligation_identity TEXT,
            obligation_type TEXT, due_date DATE, direction TEXT, status TEXT);
        CREATE TABLE staff_obligations (case_no TEXT, obligation_identity TEXT,
            obligation_kind TEXT, due_date DATE, staff_id INTEGER, direction TEXT, status TEXT);
        CREATE TABLE staff (id INTEGER, name TEXT);
        CREATE TABLE client_legacy_virtual_accounts (case_no TEXT, virtual_account TEXT);
        INSERT INTO clients VALUES (1,'客戶甲',NULL,'新竹市','東區','一般市民');
        INSERT INTO clients VALUES (2,'客戶乙',NULL,NULL,NULL,'補助市民');
        INSERT INTO orders VALUES ('115000101',1,20,1,'2026-07-01','訂單完成','2026-09-15','2026-08-20');
        INSERT INTO orders VALUES ('115000102',2,40,0,'2026-12-01','歷史訂單－服務完成',NULL,NULL);
        INSERT INTO staff VALUES (7,'月嫂甲');
        INSERT INTO staff VALUES (8,'月嫂乙');
        INSERT INTO client_obligations VALUES ('115000101','c-deposit','deposit','2026-06-20','receivable_from_client','settled');
        INSERT INTO client_obligations VALUES ('115000101','c-first','first','2026-07-03','receivable_from_client','open');
        INSERT INTO client_obligations VALUES ('115000101','c-second','second',NULL,'receivable_from_client','open');
        INSERT INTO client_obligations VALUES ('115000101','c-return-1','subsidy_return','2026-10-15','payable_to_client','open');
        INSERT INTO client_obligations VALUES ('115000101','c-return-2','subsidy_return','2026-11-15','payable_to_client','open');
        INSERT INTO client_obligations VALUES ('115000101','c-cancelled','deposit','2026-01-01','receivable_from_client','cancelled');
        INSERT INTO client_obligations VALUES ('115000101','c-wrong-direction','deposit','2026-01-02','payable_to_client','open');
        INSERT INTO staff_obligations VALUES ('115000101','s-one','service_pay','2026-10-15',7,'payable_to_staff','open');
        INSERT INTO staff_obligations VALUES ('115000101','s-two','adjustment','2026-08-15',8,'payable_to_staff','settled');
        INSERT INTO staff_obligations VALUES ('115000101','s-no-name','service_pay',NULL,9,'payable_to_staff','open');
        INSERT INTO staff_obligations VALUES ('115000101','s-cancelled','service_pay','2026-01-01',7,'payable_to_staff','cancelled');
        INSERT INTO staff_obligations VALUES ('115000101','s-recovery','reversal','2026-01-02',7,'receivable_from_staff','open');
    """)

    def no_amount_calculation(*_, **__):
        raise AssertionError("registry dates must not call amount/schedule calculation")

    monkeypatch.setattr(repository_module, "_finance_values", no_amount_calculation)
    monkeypatch.setattr(repository_module, "load_contract_client_finance_facts", no_amount_calculation)
    monkeypatch.setattr(repository_module, "build_client_finance_terms_candidate", no_amount_calculation)
    # Virtual-account calculation is unchanged and outside this test boundary.
    monkeypatch.setattr(repository_module, "build_client_virtual_account", lambda _: None)
    yield connection
    connection.db.close()


def _page(connection, **options):
    application = ClientRegistryQueryApplication(
        repository_module.MySqlClientRegistryQueryRepository(connection)
    )
    return application.list(query=options.get("query"), limit=options.get("limit", 100), after=options.get("after"))


def test_stored_values_survive_query_and_http_serialization(connection):
    page = _page(connection)
    assert [item.case_no for item in page.items] == ["115000101", "115000102"]
    payload = ClientRegistryPageView.model_validate(page, from_attributes=True).model_dump(mode="json")
    first, historical = payload["items"]
    assert first["staff_payment_due_date"] == "2026-09-15"
    assert [(entry["staff_name"], entry["due_date"]) for entry in first["staff_obligation_dates"]] == [
        ("月嫂甲", "2026-10-15"), ("月嫂乙", "2026-08-15"), (None, None),
    ]
    client = {entry["obligation_identity"]: entry["due_date"] for entry in first["client_obligation_dates"]}
    assert client == {
        "c-deposit": "2026-06-20", "c-first": "2026-07-03", "c-second": None,
        "c-return-1": "2026-10-15", "c-return-2": "2026-11-15",
    }
    assert first["claim_application_year"] == 2026
    assert first["claim_application_month"] == 10
    assert historical["staff_payment_due_date"] is None
    assert historical["client_obligation_dates"] == []
    assert historical["staff_obligation_dates"] == []
    assert historical["claim_application_year"] is None
    assert historical["claim_application_month"] is None
    assert len(connection.statements) == 4
    assert sum("FROM client_legacy_virtual_accounts" in sql for sql, _ in connection.statements) == 1
    assert not any("v_order_details" in sql or "staff_schedule" in sql for sql, _ in connection.statements)


def test_accounting_reads_are_page_bounded_without_changing_cursor(connection):
    page = _page(connection, limit=1)
    assert page.next_cursor == "115000101"
    assert len(page.items) == 1
    assert all(parameters == ("115000101",) for _, parameters in connection.statements[1:])
    next_page = _page(connection, limit=1, after=page.next_cursor)
    assert [item.case_no for item in next_page.items] == ["115000102"]
    assert next_page.next_cursor is None


def test_empty_search_needs_no_obligation_queries(connection):
    assert _page(connection, query="absent-case").items == ()
    assert len(connection.statements) == 1


def test_read_failure_is_not_reported_as_empty_dates(connection):
    connection.db.execute("DROP TABLE staff_obligations")
    with pytest.raises(sqlite3.OperationalError):
        _page(connection)


@pytest.mark.parametrize("identity,completed_on,expected", [
    ("一般市民", date(2026, 7, 20), (2026, 10)),
    ("補助市民", date(2026, 12, 20), (2027, 1)),
    ("低收入戶", date(2026, 8, 20), (2026, 10)),
    ("非市民", date(2026, 8, 20), (None, None)),
    ("一般市民", None, (None, None)),
])
def test_reuses_existing_month_projection_without_fabricating_a_date(identity, completed_on, expected):
    result = repository_module._claim_application_month({
        "identity_status": identity, "actual_end_date": completed_on,
        "end_date": date(2026, 9, 30),
    })
    assert (result["claim_application_year"], result["claim_application_month"]) == expected
    assert set(result) == {"claim_application_year", "claim_application_month"}


def test_dates_are_not_added_to_registry_mutation_input():
    with pytest.raises(ValidationError):
        ClientProfileChangeSet.model_validate({"staff_payment_due_date": "2026-09-15"})
