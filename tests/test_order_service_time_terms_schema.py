from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT
    / "db"
    / "schema_parts"
    / "105_order_service_time_terms.sql"
)


def _schema_sql() -> str:
    raw = SCHEMA_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_service_time_terms_are_nullable_additive_columns() -> None:
    sql = _compact(_schema_sql())

    assert (
        "add column `service_start_time` time null"
        in sql
    )
    assert "add column `service_end_time` time null" in sql
    assert (
        "add column `service_end_day_offset` tinyint unsigned null"
        in sql
    )
    assert "column_name = 'service_start_time'" in sql
    assert "column_name = 'service_end_time'" in sql
    assert "column_name = 'service_end_day_offset'" in sql
    assert "data_type = 'time'" in sql
    assert "column_type = 'tinyint unsigned'" in sql


def test_service_time_terms_require_all_null_or_all_complete() -> None:
    sql = _compact(_schema_sql())

    assert "chk_orders_service_time_terms_complete" in sql
    assert (
        "`service_start_time` is null "
        "and `service_end_time` is null "
        "and `service_end_day_offset` is null"
    ) in sql
    assert (
        "`service_start_time` is not null "
        "and `service_end_time` is not null "
        "and `service_end_day_offset` is not null"
    ) in sql
    assert "chk_orders_service_end_day_offset" in sql
    assert "`service_end_day_offset` in (0, 1)" in sql


def test_replay_validates_exact_column_and_check_metadata() -> None:
    sql = _compact(_schema_sql())

    assert sql.count("information_schema.columns") >= 6
    assert sql.count("information_schema.check_constraints") == 2
    assert sql.count("tc.enforced = 'yes'") == 2
    assert "fail_closed_service_start_time_invalid_spec" in sql
    assert "fail_closed_service_end_time_invalid_spec" in sql
    assert "fail_closed_service_end_day_offset_invalid_spec" in sql
    assert "fail_closed_service_time_terms_complete_check_invalid_spec" in sql
    assert "fail_closed_service_end_day_offset_check_invalid_spec" in sql


def test_migration_never_backfills_or_mutates_existing_rows() -> None:
    sql = _compact(_schema_sql())

    forbidden = (
        r"\bupdate\s+orders\b",
        r"\binsert\s+into\s+orders\b",
        r"\bdelete\s+from\s+orders\b",
        r"\bdrop\s+table\b",
        r"\bservice_time\b.*\bclients\b",
    )
    assert all(re.search(pattern, sql) is None for pattern in forbidden)
