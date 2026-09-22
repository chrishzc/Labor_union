"""Focused checks for the retired Assignment Schedule DDL entry."""

from __future__ import annotations

from pathlib import Path


from scripts import migrate_assignment_schedule_integrity as migration


def test_source_contains_no_importable_direct_ddl_writer() -> None:
    source = Path(migration.__file__).read_text(encoding="utf-8")

    assert "def apply_migration(" not in source
    assert "ALTER TABLE staff_schedule" not in source
    assert ".commit(" not in source


def test_read_only_helpers_remain_deterministic() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.rows = []

        def execute(self, query, params=None) -> None:
            compact = " ".join(query.split())
            if "INFORMATION_SCHEMA.COLUMNS" in compact or "TABLE_CONSTRAINTS" in compact:
                self.rows = [(1,)]
            elif "INFORMATION_SCHEMA.STATISTICS" in compact:
                self.rows = [
                    ("ukey_staff_date", 0, "work_date", 2),
                    ("ukey_staff_date", 0, "staff_id", 1),
                ]
            else:
                self.rows = []

        def fetchone(self):
            return self.rows[0]

        def fetchall(self):
            return self.rows

    receipt = migration.run_checks(Cursor(), "lu_test_task97")

    assert receipt["mode"] == "check"
    assert receipt["index_status"]["ukey_staff_date_valid"] is True
    assert receipt["success"] is True


def test_database_configuration_has_no_target_or_credential_fallback(monkeypatch) -> None:
    for name in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)

    config = migration.get_db_config()

    assert config["host"] == ""
    assert config["user"] == ""
    assert config["password"] == ""
    assert config["database"] == ""
