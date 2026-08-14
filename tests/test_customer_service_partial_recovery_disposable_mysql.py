"""
File: test_customer_service_partial_recovery_disposable_mysql.py
Description: 以一次性 MySQL 驗證客服 runtime 的既知 partial 可在候選 DB 安全續跑。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from scripts import migrate_preserved_database_additive_schema as migration


ROOT = Path(__file__).resolve().parents[1]
PART_185 = ROOT / "db/schema_parts/185_customer_service_runtime.sql"
RECOVERABLE = frozenset({PART_185.name})


def _config() -> migration.DatabaseConfig:
    if not os.getenv("MYSQL_TEST_CONTAINER"):
        pytest.skip("requires an explicitly configured disposable MySQL container")
    return migration.config_from_env(ROOT / ".env")[0]


def _configure_release(monkeypatch: pytest.MonkeyPatch) -> None:
    descriptor = migration._canonical_artifact_descriptor(PART_185.name)
    release = SimpleNamespace(
        release_id="customer-service-partial-disposable-test",
        fingerprint="test-fingerprint",
        artifacts=({"name": PART_185.name, "relative_path": "db/schema_parts/185_customer_service_runtime.sql"},),
        required_restart_targets=(),
        post_cutover_smoke_ids=(),
        verification_contracts=(),
        descriptors={},
        backfills=(),
    )
    monkeypatch.setattr(migration, "RELEASE_MANIFEST", release)
    monkeypatch.setattr(migration, "SCHEMA_PARTS", (PART_185,))
    monkeypatch.setattr(
        migration,
        "OWNED_OBJECTS",
        {
            PART_185.name: {
                "tables": {
                    table: set(columns)
                    for table, columns in descriptor["tables"].items()
                },
                "triggers": set(),
            }
        },
    )
    monkeypatch.setattr(migration, "MANIFEST_DRIVEN_RELEASE", True)


def _create_database(config: migration.DatabaseConfig, database: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    finally:
        connection.close()


def _create_partial_source(config: migration.DatabaseConfig, database: str) -> None:
    _create_database(config, database)
    statements = migration.split_sql(PART_185.read_text(encoding="utf-8"))
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            suffix = (
                " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                "COLLATE=utf8mb4_unicode_ci"
            )
            cursor.execute(f"CREATE TABLE clients (id INT PRIMARY KEY){suffix}")
            cursor.execute(
                f"CREATE TABLE orders (case_no VARCHAR(50) PRIMARY KEY){suffix}"
            )
            cursor.execute(
                f"CREATE TABLE admin_users (id BIGINT PRIMARY KEY){suffix}"
            )
            cursor.execute(statements[0])
            cursor.execute(
                "INSERT INTO customer_service_tickets "
                "(line_user_id, category) VALUES ('U-disposable', 'other')"
            )
    finally:
        connection.close()


def _drop(config: migration.DatabaseConfig, *databases: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            for database in databases:
                assert database.startswith("lu_test_customer_service_")
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


@pytest.mark.integration
def test_customer_service_partial_upgrades_on_preserved_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    container = os.environ["MYSQL_TEST_CONTAINER"]
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_customer_service_source_{suffix}"
    candidate = f"lu_test_customer_service_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_partial_source(config, source)
        plan = migration.build_plan(config, source, candidate, RECOVERABLE)
        assert plan["source_objects"] == {PART_185.name: "partial"}
        paths = {name: tmp_path / name for name in ("plan", "dump", "backup", "operation")}
        migration.write_receipt(paths["plan"], plan)
        migration.create_source_dump(config, source, paths["dump"], paths["backup"], mysql_container=container)
        migration.restore_candidate(config, source, candidate, paths["dump"], paths["backup"], paths["operation"], mysql_container=container)
        migration.apply_schema(config, source, candidate, paths["plan"], paths["operation"], mysql_container=container, allowed_partial_artifacts=RECOVERABLE)

        candidate_state = migration._owned_classification(migration._schema_snapshot(config, candidate))
        source_state = migration._owned_classification(migration._schema_snapshot(config, source))
        assert candidate_state == {PART_185.name: "exact"}
        assert source_state == {PART_185.name: "partial"}
    finally:
        _drop(config, candidate, source)
