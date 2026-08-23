"""
File: test_human_escalation_mysql_preserve_data.py
Description: 驗證客服 escalation additive release 與 disposable MySQL preserve 契約。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

import pytest

import scripts.migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from scripts.verify_validation_schema_manifest import load_manifest, verify_manifest
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[2]
PART_NAME = "1002_customer_service_human_escalation.sql"
PART_PATH = ROOT / "db/schema_parts" / PART_NAME
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_21_customer_service_human_escalation_v1.json"
)
DESCRIPTOR_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_21_customer_service_human_escalation_v1.descriptors.json"
)


def test_m4_db_part_is_additive_and_events_are_immutable() -> None:
    sql = PART_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS customer_service_escalations" in sql
    assert "CREATE TABLE IF NOT EXISTS customer_service_escalation_events" in sql
    assert "ALTER TABLE" not in sql.upper()
    assert "INSERT " not in sql.upper()
    assert "UPDATE customer_service_escalations" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "BEFORE UPDATE ON customer_service_escalation_events" in sql
    assert "BEFORE DELETE ON customer_service_escalation_events" in sql
    assert "customer_service_tickets(id)" in sql


def test_m4_db_manifest_descriptor_and_assembly_are_hash_locked() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert manifest.release_id == "labor-union-customer-service-human-escalation-2026-08-21-v1"
    assert manifest.schema_paths(ROOT)[0].name == PART_NAME
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assert descriptor["release_id"] == manifest.release_id
    owned = descriptor["descriptors"][PART_NAME]
    assert set(owned["tables"]) == {
        "customer_service_escalations",
        "customer_service_escalation_events",
    }
    assert len(owned["indexes"]) == 12
    assert len(owned["foreign_keys"]) == 2
    assert len(owned["checks"]) == 12
    assert len(owned["triggers"]) == 2
    previous_parts = migration.SCHEMA_PARTS
    migration.SCHEMA_PARTS = (PART_PATH,)
    try:
        released = manifest.owned_object_descriptors(ROOT)[PART_NAME]
        canonical = migration._canonical_artifact_descriptor(PART_NAME)
        assert set(released["tables"]) == set(canonical["tables"])
        for kind in ("indexes", "foreign_keys", "checks"):
            assert released[kind] == canonical[kind]
        assert set(released["triggers"]) == set(canonical["triggers"])
    finally:
        migration.SCHEMA_PARTS = previous_parts
    assembly = load_schema_assembly()
    assert PART_NAME in {path.name for path in assembly.active_artifact_paths}
    assert verify_manifest(load_manifest()) == []


def test_m4_db_release_has_no_seed_backfill_or_destructive_effect() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["backfills"] == []
    assert payload["artifacts"][0]["data_effect"] == "schema_only"
    assert "customer-service-human-escalation-v1" in payload["application_compatibility"]["compatible_contracts"]


def _config() -> migration.DatabaseConfig:
    if not os.getenv("MYSQL_TEST_CONTAINER"):
        pytest.skip("BLOCKED_ENGINE_EVIDENCE: disposable MySQL container is not configured")
    return migration.config_from_env(ROOT / ".env")[0]


@pytest.mark.integration
def test_m4_db_preserves_representative_ticket_on_disposable_mysql() -> None:
    """Use only lu_test_* databases; never route this test to configured source."""
    config = _config()
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_m4_escalation_source_{suffix}"
    candidate = f"lu_test_m4_escalation_candidate_{suffix}"
    connection = config.connect(timeout_seconds=20)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{source}` CHARACTER SET utf8mb4")
            cursor.execute(f"CREATE DATABASE `{candidate}` CHARACTER SET utf8mb4")
        connection.close()
        source_connection = config.connect(source, timeout_seconds=20)
        try:
            with source_connection.cursor() as cursor:
                cursor.execute("CREATE TABLE customer_service_tickets (id BIGINT PRIMARY KEY, category VARCHAR(64) NOT NULL)")
                cursor.execute("INSERT INTO customer_service_tickets (id, category) VALUES (1, 'other')")
        finally:
            source_connection.close()
        candidate_connection = config.connect(candidate, timeout_seconds=20)
        try:
            with candidate_connection.cursor() as cursor:
                cursor.execute("CREATE TABLE customer_service_tickets (id BIGINT PRIMARY KEY, category VARCHAR(64) NOT NULL)")
                cursor.execute("INSERT INTO customer_service_tickets (id, category) VALUES (1, 'other')")
                for statement in migration.split_sql(PART_PATH.read_text(encoding="utf-8")):
                    cursor.execute(statement)
                cursor.execute("SELECT COUNT(*) AS count FROM customer_service_tickets")
                assert cursor.fetchone()["count"] == 1
                cursor.execute("SELECT COUNT(*) AS count FROM customer_service_escalations")
                assert cursor.fetchone()["count"] == 0
                cursor.execute("SELECT COUNT(*) AS count FROM customer_service_escalation_events")
                assert cursor.fetchone()["count"] == 0
        finally:
            candidate_connection.close()
    finally:
        cleanup = config.connect(timeout_seconds=20)
        try:
            with cleanup.cursor() as cursor:
                for database in (candidate, source):
                    cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            cleanup.close()
