"""
File: test_wp79_line_runtime_recovery_disposable_mysql.py
Description: 以一次性 MySQL 驗證舊版 LINE 身分 schema 可在候選 DB 安全續跑 186。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from scripts import migrate_preserved_database_additive_schema as migration


ROOT = Path(__file__).resolve().parents[1]
PART_186 = ROOT / "db/schema_parts/186_line_identity_management.sql"
RECOVERABLE = frozenset({PART_186.name})


def _config() -> migration.DatabaseConfig:
    if not os.getenv("MYSQL_TEST_CONTAINER"):
        pytest.skip("requires an explicitly configured disposable MySQL container")
    return migration.DatabaseConfig(
        os.getenv("DB_HOST", "127.0.0.1"),
        int(os.getenv("DB_PORT", "3306")),
        os.getenv("DB_USER", "root"),
        os.getenv("DB_PASSWORD", ""),
    )


def _configure_release(monkeypatch: pytest.MonkeyPatch) -> None:
    release = SimpleNamespace(
        release_id="wp79-disposable-test",
        fingerprint="test-fingerprint",
        artifacts=({"name": PART_186.name, "relative_path": "db/schema_parts/186_line_identity_management.sql"},),
        required_restart_targets=(),
        post_cutover_smoke_ids=(),
        verification_contracts=(),
        descriptors={},
        backfills=(),
    )
    monkeypatch.setattr(migration, "RELEASE_MANIFEST", release)
    monkeypatch.setattr(migration, "SCHEMA_PARTS", (PART_186,))
    monkeypatch.setattr(migration, "OWNED_OBJECTS", {
        PART_186.name: {"tables": {}, "triggers": set()},
    })
    monkeypatch.setattr(migration, "MANIFEST_DRIVEN_RELEASE", True)


def _create_legacy_source(config: migration.DatabaseConfig, database: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    finally:
        connection.close()
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE line_rich_menu_publications "
                "(id BIGINT PRIMARY KEY) ENGINE=InnoDB "
                "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cursor.execute(
                "CREATE TABLE line_identity_bindings ("
                "line_user_id VARCHAR(191) PRIMARY KEY,"
                "binding_status ENUM('unbound','pending_review','bound','revoked') "
                "NOT NULL DEFAULT 'unbound',"
                "subject_type ENUM('customer','staff','admin') NULL,"
                "subject_reference VARCHAR(191) NULL,"
                "active_subject_key VARCHAR(400) GENERATED ALWAYS AS ("
                "CASE WHEN binding_status IN ('pending_review','bound') "
                "THEN CONCAT(subject_type, ':', subject_reference) ELSE NULL END"
                ") STORED) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                "COLLATE=utf8mb4_unicode_ci"
            )
            cursor.execute(
                "CREATE TABLE line_identity_binding_events ("
                "id BIGINT PRIMARY KEY,"
                "action ENUM('claim_submitted','bound','revoked','rebound','legacy_imported') "
                "NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                "COLLATE=utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def _drop(config: migration.DatabaseConfig, *databases: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            for database in databases:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


@pytest.mark.integration
def test_legacy_line_identity_schema_upgrades_on_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    container = os.environ["MYSQL_TEST_CONTAINER"]
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp79_source_{suffix}"
    candidate = f"lu_test_wp79_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_legacy_source(config, source)
        plan = migration.build_plan(config, source, candidate, RECOVERABLE)
        assert plan["source_objects"] == {PART_186.name: "partial"}
        plan_path = tmp_path / "plan.json"
        dump_path = tmp_path / "source.sql"
        backup_path = tmp_path / "backup.json"
        operation_path = tmp_path / "operation.json"
        migration.write_receipt(plan_path, plan)
        migration.create_source_dump(config, source, dump_path, backup_path, mysql_container=container)
        migration.restore_candidate(config, source, candidate, dump_path, backup_path, operation_path, mysql_container=container)
        migration.apply_schema(config, source, candidate, plan_path, operation_path, mysql_container=container, allowed_partial_artifacts=RECOVERABLE)

        candidate_state = migration._owned_classification(
            migration._schema_snapshot(config, candidate)
        )
        source_state = migration._owned_classification(
            migration._schema_snapshot(config, source)
        )
        assert candidate_state == {PART_186.name: "exact"}
        assert source_state == {PART_186.name: "partial"}
    finally:
        _drop(config, candidate, source)
