from pathlib import Path
import re

from scripts.migrate_preserved_database_additive_schema import (
    _system_alert_projection_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT
    / "db"
    / "schema_parts"
    / "107_system_alert_current_projection.sql"
)


def _sql() -> str:
    raw = SCHEMA_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8", errors="strict")


def _column(
    name: str, column_type: str, nullable: str, default=None, extra: str = ""
) -> dict:
    return {
        "table_name": "system_alerts",
        "column_name": name,
        "column_type": column_type,
        "is_nullable": nullable,
        "column_default": default,
        "extra": extra,
    }


def _legacy_snapshot() -> dict:
    return {
        "columns": [
            _column("id", "int", "NO", extra="auto_increment"),
            _column("event_type", "varchar(50)", "NO"),
            _column("description", "text", "NO"),
            _column("status", "enum('pending','resolved')", "YES", "pending"),
            _column("created_at", "timestamp", "YES", "CURRENT_TIMESTAMP"),
            _column("resolved_at", "timestamp", "YES"),
            _column("resolved_by", "varchar(50)", "YES"),
        ],
        "indexes": [],
    }


def test_legacy_shape_is_absent_and_torn_statement_is_drift() -> None:
    snapshot = _legacy_snapshot()
    assert _system_alert_projection_state(snapshot) == "absent"
    snapshot["columns"].append(_column("alert_code", "varchar(50)", "YES"))
    assert _system_alert_projection_state(snapshot) == "drift"


def test_migration_preserves_legacy_columns_and_maps_pending_to_open() -> None:
    sql = re.sub(r"\s+", " ", _sql()).lower()

    assert "modify column `event_type` varchar(50) null" in sql
    assert "modify column `description` text null" in sql
    assert "`case_key` = concat(''legacy-alert:'', `id`)" in sql
    assert "`status` = if(`status` = ''pending'', ''open'', ''resolved'')" in sql
    assert "legacy_event_type" in sql
    assert "system_alert_current_projection_v1" in sql
    assert "legacy_description" not in sql
    assert "drop table" not in sql
    assert "delete from `system_alerts`" not in sql


def test_migration_installs_current_writer_contract_and_indexes() -> None:
    sql = re.sub(r"\s+", " ", _sql()).lower()

    for fragment in (
        "modify column `alert_code` varchar(50) not null",
        "modify column `source_domain` varchar(50) not null",
        "modify column `case_key` varchar(100) not null",
        "modify column `reason` varchar(500) not null",
        "modify column `details` json not null",
        "enum(''open'',''claimed'',''resolved'') not null default ''open''",
        "add unique key `uq_alert_case` (`alert_code`, `case_key`)",
        "add index `idx_system_alert_status` (`status`)",
    ):
        assert fragment in sql
