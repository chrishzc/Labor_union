from pathlib import Path

from scripts.bootstrap_disposable_mysql_schema import (
    _base_schema_for,
    _partition_base_statements,
    _require_disposable_database,
)


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
