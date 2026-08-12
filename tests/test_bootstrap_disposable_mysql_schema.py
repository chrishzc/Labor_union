from pathlib import Path
import re

from scripts.bootstrap_disposable_mysql_schema import (
    _base_schema_for,
    _partition_base_statements,
    _require_disposable_database,
    _require_absent_database,
    _schema_bootstrap_gate_errors,
)
from scripts.init_db import _schema_part_sort_key


def test_disposable_schema_bootstrap_requires_exact_lu_test_confirmation():
    assert _require_disposable_database("lu_test_finance", "lu_test_finance") == "lu_test_finance"


def test_disposable_schema_bootstrap_rejects_union_db_and_keeps_it_out_of_base_ddl():
    try:
        _require_disposable_database("union_db", "union_db")
    except ValueError as error:
        assert str(error) == "database must start with lu_test_"
    else:
        raise AssertionError("union_db must never be accepted")

    assert "union_db" not in _base_schema_for("lu_test_finance")
    assert "CREATE DATABASE lu_test_finance" in _base_schema_for("lu_test_finance")


def test_disposable_bootstrap_loads_the_lifecycle_view_from_the_final_schema_part():
    statements, views = _partition_base_statements("lu_test_finance")

    assert views == []
    assert all("CREATE OR REPLACE VIEW" not in statement for statement in statements)
    view_part = Path(__file__).parents[1] / "db" / "schema_parts" / "999_v_order_details_view.sql"
    view_sql = view_part.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW v_order_details" in view_sql
    assert "lifecycle_version" in view_sql


def test_schema_part_sort_places_lettered_99_parts_before_part_100(tmp_path):
    paths = [
        tmp_path / "100_runtime.sql",
        tmp_path / "99b_locks.sql",
        tmp_path / "99a_events.sql",
        tmp_path / "99_matching.sql",
    ]

    assert [path.name for path in sorted(paths, key=_schema_part_sort_key)] == [
        "99_matching.sql",
        "99a_events.sql",
        "99b_locks.sql",
        "100_runtime.sql",
    ]


def test_disposable_bootstrap_refuses_to_overwrite_an_existing_database():
    existing_cursor = _DatabaseCursor(("lu_test_finance",))

    try:
        _require_absent_database(existing_cursor, "lu_test_finance")
    except RuntimeError as error:
        assert str(error) == "disposable database already exists; refusing to overwrite it"
    else:
        raise AssertionError("existing database must not be overwritten")

    _require_absent_database(_DatabaseCursor(None), "lu_test_finance")


def test_schema_bootstrap_gate_requires_inputs_but_not_historical_execution_receipts():
    gate = {
        "errors": {
            "baseline": [],
            "scenarios": [],
            "fixtures": [],
            "field_authority": [],
            "receipts": ["historical receipt digest is stale"],
        }
    }

    assert _schema_bootstrap_gate_errors(gate) == []


def test_schema_bootstrap_gate_rejects_invalid_scenario_contracts():
    gate = {
        "errors": {
            "baseline": [],
            "scenarios": ["missing business requirement mapping"],
            "fixtures": [],
            "field_authority": [],
            "receipts": [],
        }
    }

    assert _schema_bootstrap_gate_errors(gate) == [
        "scenarios: missing business requirement mapping"
    ]


def test_every_multiline_trigger_declares_its_timing_and_table() -> None:
    schema_parts = Path("db/schema_parts")
    incomplete = [
        path.name
        for path in schema_parts.glob("*.sql")
        if re.search(r"CREATE TRIGGER[^\r\n]*\r?\nFOR EACH ROW", path.read_text(encoding="utf-8"))
    ]

    assert incomplete == []




class _DatabaseCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))

    def fetchone(self):
        return self.row
