"""
File: test_wp78_partial_recovery_disposable_mysql.py
Description: 以一次性 MySQL 驗證 Knowledge partial source 的備份、候選升級與資料保留。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from scripts import migrate_preserved_database_additive_schema as migration


ROOT = Path(__file__).resolve().parents[1]
PART_148 = ROOT / "db/schema_parts/148_knowledge_retrieval.sql"
PART_163 = ROOT / "db/schema_parts/163_knowledge_runtime.sql"
RECOVERABLE = frozenset({PART_148.name, PART_163.name})


def _config() -> migration.DatabaseConfig:
    if not os.getenv("MYSQL_TEST_CONTAINER"):
        pytest.skip("requires an explicitly configured disposable MySQL container")
    return migration.config_from_env(ROOT / ".env")[0]


def _configure_recovery_release(monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = tuple({
        "name": part.name,
        "relative_path": part.relative_to(ROOT).as_posix(),
    } for part in (PART_148, PART_163))
    release = SimpleNamespace(
        release_id="wp78-disposable-test",
        fingerprint="test-fingerprint",
        artifacts=artifacts,
        required_restart_targets=(),
        post_cutover_smoke_ids=(),
        verification_contracts=(),
        descriptors={},
        backfills=(),
    )
    monkeypatch.setattr(migration, "RELEASE_MANIFEST", release)
    monkeypatch.setattr(migration, "SCHEMA_PARTS", (PART_148, PART_163))
    monkeypatch.setattr(migration, "OWNED_OBJECTS", {
        PART_148.name: {"tables": {}, "triggers": set()},
        PART_163.name: {"tables": {}, "triggers": set()},
    })
    monkeypatch.setattr(migration, "MANIFEST_DRIVEN_RELEASE", True)


def _create_partial_source(config: migration.DatabaseConfig, database: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    finally:
        connection.close()
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE admin_users (id BIGINT PRIMARY KEY)")
            cursor.execute(
                "CREATE TABLE line_delivery_tasks "
                "(id BIGINT UNSIGNED PRIMARY KEY)"
            )
            for statement in migration.split_sql(PART_148.read_text("utf-8")):
                cursor.execute(statement)
            runtime = migration.split_sql(PART_163.read_text("utf-8"))
            for statement in runtime[:3]:
                cursor.execute(statement)
            cursor.execute("DROP TABLE knowledge_apply_receipts")
            cursor.execute("INSERT INTO admin_users (id) VALUES (1)")
            cursor.execute(
                "INSERT INTO knowledge_items "
                "(source_uri,source_trust_tier,title,content,content_digest,"
                "created_by_admin_user_id) VALUES "
                "('wp78','internal_policy','title','content',%s,1)",
                ("a" * 64,),
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
def test_partial_source_is_backed_up_and_upgraded_on_a_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    container = os.environ["MYSQL_TEST_CONTAINER"]
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp78_source_{suffix}"
    candidate = f"lu_test_wp78_candidate_{suffix}"
    _configure_recovery_release(monkeypatch)
    try:
        _create_partial_source(config, source)
        plan = migration.build_plan(config, source, candidate, RECOVERABLE)
        assert plan["source_objects"] == {
            PART_148.name: "partial",
            PART_163.name: "partial",
        }
        plan_path = tmp_path / "plan.json"
        dump_path = tmp_path / "source.sql"
        backup_path = tmp_path / "backup.json"
        operation_path = tmp_path / "operation.json"
        migration.write_receipt(plan_path, plan)
        migration.create_source_dump(
            config, source, dump_path, backup_path,
            mysql_container=container,
        )
        migration.restore_candidate(
            config, source, candidate, dump_path, backup_path, operation_path,
            mysql_container=container,
        )
        migration.apply_schema(
            config, source, candidate, plan_path, operation_path,
            mysql_container=container,
            allowed_partial_artifacts=RECOVERABLE,
        )
        receipt = migration.read_receipt(operation_path)
        candidate_state = migration._owned_classification(
            migration._schema_snapshot(config, candidate)
        )
        source_snapshot = migration._schema_snapshot(config, source)
        preservation = migration._verify_knowledge_source_identity_backfill(
            config, source, candidate, source_snapshot
        )

        assert receipt["status"] == "backfilled"
        assert candidate_state == {
            PART_148.name: "exact",
            PART_163.name: "exact",
        }
        assert preservation["rows"] == 1
    finally:
        _drop(config, candidate, source)


@pytest.mark.integration
def test_partial_table_columns_still_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    source = f"lu_test_wp78_drift_{uuid.uuid4().hex[:10]}"
    candidate = source.replace("drift", "candidate")
    _configure_recovery_release(monkeypatch)
    try:
        _create_partial_source(config, source)
        connection = config.connect(source)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE knowledge_apply_receipts "
                    "(idempotency_key VARCHAR(191) PRIMARY KEY)"
                )
        finally:
            connection.close()

        with pytest.raises(
            migration.UpgradeBlocked,
            match="partial/drift owned objects",
        ):
            migration.build_plan(config, source, candidate, RECOVERABLE)
    finally:
        _drop(config, candidate, source)
