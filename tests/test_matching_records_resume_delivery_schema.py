from __future__ import annotations

from pathlib import Path

from scripts.migrate_preserved_database_additive_schema import (
    _matching_records_resume_delivery_state,
    split_sql,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PART = (
    ROOT / "db" / "schema_parts" / "108_matching_records_resume_delivery.sql"
)
REQUIRED_COLUMNS = {
    "id", "case_no", "staff_id", "caregiver_accepted",
    "sent_at", "replied_at", "sent_info_1_at", "sent_info_2_at",
}


def _snapshot(*, sent_resume: dict[str, object] | None = None):
    columns = [
        {
            "table_name": "matching_records",
            "column_name": name,
            "column_type": "varchar(50)",
            "is_nullable": "YES",
            "column_default": None,
            "extra": "",
            "generation_expression": "",
        }
        for name in sorted(REQUIRED_COLUMNS)
    ]
    if sent_resume is not None:
        columns.append(
            {
                "table_name": "matching_records",
                "column_name": "sent_resume_at",
                **sent_resume,
            }
        )
    return {"columns": columns, "indexes": [], "triggers": [], "views": []}


def test_resume_delivery_classifier_is_exact_and_fail_closed() -> None:
    assert _matching_records_resume_delivery_state(_snapshot()) == "absent"
    assert _matching_records_resume_delivery_state(
        _snapshot(
            sent_resume={
                "column_type": "datetime",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
                "generation_expression": "",
            }
        )
    ) == "exact"
    assert _matching_records_resume_delivery_state(
        _snapshot(
            sent_resume={
                "column_type": "datetime",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
                "generation_expression": "",
            }
        )
    ) == "drift"
    partial = _snapshot()
    partial["columns"] = partial["columns"][:-1]
    assert _matching_records_resume_delivery_state(partial) == "partial"


def test_schema_part_is_idempotent_additive_and_never_backfills() -> None:
    raw = SCHEMA_PART.read_bytes()
    sql = raw.decode("utf-8")
    statements = split_sql(sql)
    assert statements
    assert "ADD COLUMN `sent_resume_at` DATETIME NULL" in sql
    assert "COLUMN_DEFAULT IS NULL" in sql
    assert "COALESCE(GENERATION_EXPRESSION, '') = ''" in sql
    assert "FAIL_CLOSED_SENT_RESUME_AT_INVALID_SPEC" in sql
    upper = sql.upper()
    assert "UPDATE `MATCHING_RECORDS`" not in upper
    assert "DELETE FROM `MATCHING_RECORDS`" not in upper
    assert "DROP COLUMN" not in upper
