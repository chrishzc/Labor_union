"""Excel roster predicates: whole-list selection, blanks, dates and HTTP bounds."""

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_registry_reader
from api.dependencies.client_registry import get_client_registry_query_application
from api.routes.client_registry import router
from infrastructure.mysql import client_registry_query_repository as adapter
from subsystems.client_profile.registry_filters import RegistryColumnFilter, parse_column_filters
from subsystems.client_profile.registry_query import ClientRegistryQueryApplication
from subsystems.client_profile.order_accounting_export import (
    ClientRegistryOrderAccountingExportApplication, OrderAccountingExportQuery,
)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.result = self.connection.execute(statement.replace("%s", "?"), parameters)

    def fetchall(self):
        return tuple(dict(row) for row in self.result.fetchall())


class _Connection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return _Cursor(self.connection)


@pytest.fixture
def roster(monkeypatch):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.create_function("LOCATE", 2, lambda needle, text: (text or "").find(needle) + 1)
    connection.create_function("JSON_VALID", 1, lambda value: int(value is not None))
    connection.create_function("JSON_EXTRACT", 2, lambda *_: None)
    connection.create_function("JSON_UNQUOTE", 1, lambda value: value)
    connection.executescript("""
        CREATE TABLE clients(id INTEGER,name TEXT,phone TEXT,city TEXT,address TEXT,service_type TEXT,identity_status TEXT);
        CREATE TABLE orders(case_no TEXT,client_id INTEGER,service_days INTEGER,requires_cooking INTEGER,start_date TEXT,status TEXT,staff_payment_due_date TEXT,actual_end_date TEXT);
        CREATE TABLE beclass_records(id INTEGER,bound_case_no TEXT,survey_details TEXT);
        CREATE TABLE beclass_record_correction_states(beclass_record_id INTEGER,effective_values_json TEXT);
        CREATE TABLE client_obligations(case_no TEXT,status TEXT,obligation_type TEXT,direction TEXT,due_date TEXT);
    """)
    for number in range(1, 206):
        connection.execute("INSERT INTO clients VALUES(?,?,?,?,?,?,?)", (
            number, f"測試客戶{number:03}", None, "", "東區測試路" if number % 2 else "未辨識地址", "連續服務", "",
        ))
        connection.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)", (
            f"TEST-{number:03}", number, 26, (None if number % 3 == 0 else number % 2),
            "2026-10-01", "訂單取消" if number <= 100 else "服務中", None, None,
        ))
    monkeypatch.setattr(adapter, "_load_imported_virtual_accounts", lambda cursor, cases: {case: () for case in cases})
    monkeypatch.setattr(adapter, "_load_obligation_dates", lambda cursor, cases: {case: {"client_obligation_dates": [], "staff_obligation_dates": []} for case in cases})
    yield connection, adapter.MySqlClientRegistryQueryRepository(_Connection(connection))
    connection.close()


def _matching(connection, filters):
    where, parameters = adapter._registry_filters(query=None, multi_birth_count=None, order_status=None, requires_cooking=None, after=None, column_filters=filters)
    statement = "SELECT o.case_no FROM orders o JOIN clients c ON c.id=o.client_id WHERE " + " AND ".join(where) + " ORDER BY o.case_no"
    return [row[0] for row in connection.execute(statement.replace("%s", "?"), parameters)]


def test_filters_run_before_pagination_and_options_include_values_outside_first_page(roster):
    _, repository = roster
    application = ClientRegistryQueryApplication(repository)
    predicates = (RegistryColumnFilter("order_status", "in", ("服務中",)),)
    first = application.list(query=None, column_filters=predicates, limit=100, after=None)
    second = application.list(query=None, column_filters=predicates, limit=100, after=None, offset=first.next_offset)
    assert len(first.items) == 100 and first.items[0].case_no == "TEST-101"
    assert [item.case_no for item in second.items] == [f"TEST-{number}" for number in range(201, 206)]
    assert second.next_offset is None
    options = application.filter_options(field="name", search="205")
    assert options.values == ("測試客戶205",)
    assert options.next_offset is None
    first_options = application.filter_options(field="name")
    assert len(first_options.values) == 100 and first_options.next_offset == 100
    assert application.filter_options(field="name", offset=100).next_offset == 200


def test_same_column_or_cross_column_and_and_false_are_distinct_from_blank(roster):
    connection, _ = roster
    assert _matching(connection, (
        RegistryColumnFilter("case_no", "in", ("TEST-101", "TEST-102", "TEST-103")),
        RegistryColumnFilter("requires_cooking", "in", ("false", None)),
    )) == ["TEST-102"]
    assert _matching(connection, (
        RegistryColumnFilter("case_no", "in", ("TEST-101", "TEST-102", "TEST-104")),
        RegistryColumnFilter("requires_cooking", "in", ("false",)),
    )) == ["TEST-104"]
    assert _matching(connection, (RegistryColumnFilter("order_status", "in", ()),)) == []


def test_deselect_from_all_keeps_unloaded_values_and_blank(roster):
    connection, _ = roster
    selected = _matching(connection, (RegistryColumnFilter("name", "not_in", ("測試客戶001",)),))
    assert len(selected) == 204 and "TEST-205" in selected and "TEST-001" not in selected
    assert len(_matching(connection, (RegistryColumnFilter("requires_cooking", "not_in", ("true", "false")),))) == 68
    assert len(_matching(connection, (RegistryColumnFilter("requires_cooking", "not_in", (None,)),))) == 137


def test_address_district_and_literal_text_predicates_use_displayed_values(roster):
    connection, repository = roster
    assert repository.filter_options(field="district", search=None, limit=100, offset=0).values == (None, "東區")
    assert len(_matching(connection, (RegistryColumnFilter("district", "blank"),))) == 102
    connection.execute("UPDATE clients SET name='測試%_客戶' WHERE id=1")
    assert _matching(connection, (RegistryColumnFilter("name", "contains", ("%_",)),)) == ["TEST-001"]
    assert _matching(connection, (RegistryColumnFilter("name", "equals", ("' OR 1=1 --",)),)) == []


def test_date_predicates_keep_one_case_per_multiple_current_obligations(roster):
    connection, repository = roster
    connection.executemany("INSERT INTO client_obligations VALUES(?,?,?,?,?)", [
        ("TEST-001", "open", "deposit", "receivable_from_client", "2026-10-10"),
        ("TEST-001", "open", "deposit", "receivable_from_client", "2026-10-20"),
        ("TEST-002", "cancelled", "deposit", "receivable_from_client", "2026-10-10"),
        ("TEST-003", "open", "deposit", "receivable_from_client", None),
        ("TEST-004", "open", "deposit", "payable_to_client", "2026-10-10"),
    ])
    predicate = RegistryColumnFilter("deposit_due_date", "between", ("2026-10-01", "2026-10-31"))
    assert _matching(connection, (predicate,)) == ["TEST-001"]
    blank = _matching(connection, (RegistryColumnFilter("deposit_due_date", "blank"),))
    assert "TEST-001" not in blank and all(case in blank for case in ["TEST-002", "TEST-003", "TEST-004"])
    excluded = _matching(connection, (RegistryColumnFilter("deposit_due_date", "not_in", ("2026-10-10",)),))
    assert "TEST-001" not in excluded and "TEST-003" in excluded
    assert repository.filter_options(field="deposit_due_date", search=None, limit=100, offset=0).values == (None, "2026-10-10", "2026-10-20")


@pytest.mark.parametrize("payload", [
    "{}", "[null]", '[{"field":"name","operator":"in","values":[{}]}]',
    '[{"field":"password","operator":"in","values":["x"]}]',
    '[{"field":"requires_cooking","operator":"in","values":[false]}]',
    '[{"field":"planned_start_date","operator":"between","values":["2026-10-31","2026-10-01"]}]',
    '[{"field":"service_days","operator":"contains","values":["26"]}]',
    '[{"field":"service_days","operator":"equals","values":["1.5"]}]',
    '[{"field":"name","operator":"in","values":[]},{"field":"name","operator":"blank","values":[]}]',
])
def test_invalid_column_filter_rejected_before_query(payload):
    with pytest.raises(ValueError, match="column_filters_invalid"):
        parse_column_filters(payload)


def test_http_options_route_and_typed_validation_use_same_reader(roster):
    _, repository = roster
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_registry_reader] = lambda: object()
    app.dependency_overrides[get_client_registry_query_application] = lambda: ClientRegistryQueryApplication(repository)
    with TestClient(app) as client:
        result = client.get("/api/v1/admin/registries/clients/filter-options", params={"field": "district"})
        assert result.status_code == 200
        assert result.json()["data"] == {"values": [None, "東區"], "next_offset": None}
        invalid = client.get("/api/v1/admin/registries/clients", params={"column_filters": "{}"})
        assert invalid.status_code == 422 and invalid.json()["detail"]["error"]["category"] == "validation"
        valid = client.get("/api/v1/admin/registries/clients", params={"column_filters": json.dumps([{"field": "order_status", "operator": "in", "values": ["服務中"]}]), "limit": 100})
        assert valid.status_code == 200 and valid.json()["data"]["items"][0]["case_no"] == "TEST-101"


def test_export_preserves_the_same_typed_selection():
    class Repository:
        def query_order_accounting_rows(self, selection):
            self.selection = selection
            return ()

    repository = Repository()
    predicates = (RegistryColumnFilter("order_status", "in", ("訂單成立", "服務中")), RegistryColumnFilter("requires_cooking", "blank"))
    ClientRegistryOrderAccountingExportApplication(repository).export(OrderAccountingExportQuery(column_filters=predicates))
    assert repository.selection.column_filters == predicates
