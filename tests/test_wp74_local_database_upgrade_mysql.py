"""Two isolated MySQL acceptance directions for the WP74 local upgrade."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from infrastructure.mysql.mysql_adapter import DB_CONFIG
from scripts.bootstrap_disposable_mysql_schema import bootstrap
import scripts.migrate_preserved_database_additive_schema as migration
from scripts.reset_fake_database import split_sql


ROOT = Path(__file__).resolve().parents[1]
WP72_MANIFEST = (
    ROOT / "db/migration_releases/labor_union_2026_08_13_wp72_v1.json"
)
WP72_SCHEMA = (
    ROOT / "db/schema_parts/188_matching_preferences_and_staff_availability.sql"
)


def _configured_test_database() -> tuple[migration.DatabaseConfig, str]:
    source = str(DB_CONFIG.get("database") or "").strip()
    if not source.startswith("lu_test_"):
        pytest.skip("current configured database must be an explicit lu_test_* source")
    config = migration.DatabaseConfig(
        str(DB_CONFIG["host"]), int(DB_CONFIG["port"]),
        str(DB_CONFIG["user"]), str(DB_CONFIG["password"]),
    )
    return config, source


def _drop_completed_database(config, database: str) -> None:
    assert database.startswith(("lu_test_wp74_schema_", "lu_test_wp74_data_"))
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{database}`")
    finally:
        connection.close()


def _wp72_object_counts(config, database: str) -> tuple[int, int]:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='orders' "
                "AND column_name='requires_cooking'", (database,),
            )
            column_count = int(cursor.fetchone()["n"])
            cursor.execute(
                "SELECT COUNT(*) AS n FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name LIKE "
                "'staff_matching_preference_%%'", (database,),
            )
            preference_table_count = int(cursor.fetchone()["n"])
    finally:
        connection.close()
    return column_count, preference_table_count


@pytest.mark.integration
def test_empty_union_schema_accepts_wp72_field_upgrade() -> None:
    config, _source = _configured_test_database()
    database = f"lu_test_wp74_schema_{uuid.uuid4().hex[:12]}"
    completed = False
    try:
        bootstrap(SimpleNamespace(
            host=config.host, port=config.port, user=config.user,
            password=config.password, database=database,
            confirm_database=database, base_only=False, max_schema_part=187,
        ))
        assert _wp72_object_counts(config, database) == (0, 0)
        connection = config.connect(database)
        try:
            with connection.cursor() as cursor:
                for statement in split_sql(WP72_SCHEMA.read_text(encoding="utf-8")):
                    cursor.execute(statement)
        finally:
            connection.close()
        column_count, preference_table_count = _wp72_object_counts(config, database)
        assert column_count == 1
        assert preference_table_count == 6
        completed = True
    finally:
        if completed:
            _drop_completed_database(config, database)


@pytest.mark.integration
def test_current_database_backup_restores_and_upgrades_on_copy(tmp_path: Path) -> None:
    container = os.getenv("MYSQL_TEST_CONTAINER", "").strip()
    if not container:
        pytest.skip("requires an explicitly configured disposable MySQL container")
    config, source = _configured_test_database()
    candidate = f"lu_test_wp74_data_{uuid.uuid4().hex[:12]}"
    completed = False
    source_evidence = migration._table_evidence(config, source)
    try:
        migration.configure_release_manifests((WP72_MANIFEST,))
        source_dump = tmp_path / "current-source.sql"
        backup_receipt = tmp_path / "current-source.backup.json"
        restore_receipt = tmp_path / "candidate.restore.json"
        plan_receipt = tmp_path / "candidate.plan.json"
        migration.create_source_dump(
            config, source, source_dump, backup_receipt,
            mysql_container=container,
        )
        plan = migration.build_plan(config, source, candidate)
        assert plan["status"] == "ready"
        migration.write_receipt(plan_receipt, plan)
        migration.restore_candidate(
            config, source, candidate, source_dump, backup_receipt,
            restore_receipt, mysql_container=container,
        )
        migration.apply_schema(
            config, source, candidate, plan_receipt, restore_receipt,
            mysql_container=container,
        )
        verified = migration.verify_candidate(
            config, source, candidate, restore_receipt
        )
        assert verified["status"] == "verified"
        candidate_evidence = migration._table_evidence(config, candidate)
        for table_name, evidence in source_evidence.items():
            assert candidate_evidence[table_name]["count"] == evidence["count"]
            assert (
                candidate_evidence[table_name]["primary_key_sha256"]
                == evidence["primary_key_sha256"]
            )
        assert _wp72_object_counts(config, candidate) == (1, 6)
        completed = True
    finally:
        if completed:
            _drop_completed_database(config, candidate)
