"""
File: test_wp84_legacy_knowledge_empty_recovery.py
Description: 驗證歷史 Knowledge 空 schema 僅能在隔離候選重建，非空資料固定阻擋。
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


def _configure_release(monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = tuple({
        "name": part.name,
        "relative_path": part.relative_to(ROOT).as_posix(),
    } for part in (PART_148, PART_163))
    release = SimpleNamespace(
        release_id="wp84-disposable-test",
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
    monkeypatch.setattr(
        migration,
        "_verify_matching_records_preservation",
        lambda *_args: {"mode": "out_of_scope"},
    )


# 保持 fixture 建立在同一 helper，確保每個拒絕案例都源自同一歷史契約。
def _create_legacy_source(
    config,
    database: str,
    *,
    with_row: bool,
    with_request_job_rows: bool = False,
) -> None:
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
            for statement in migration.split_sql(_VERIFIER_SUPPORT_SQL):
                cursor.execute(statement)
            for statement in migration.split_sql(_LEGACY_KNOWLEDGE_SQL):
                cursor.execute(statement)
            if with_row:
                cursor.execute(
                    "INSERT INTO knowledge_items "
                    "(source_identity,title,source_digest,created_by_actor_id) "
                    "VALUES ('legacy:1','legacy',%s,'admin:legacy')",
                    ("a" * 64,),
                )
            if with_request_job_rows:
                cursor.execute(
                    "INSERT INTO knowledge_answer_requests "
                    "(question,request_status,idempotency_key,correlation_id) "
                    "VALUES ('legacy question','pending','request:legacy','correlation:legacy')"
                )
                cursor.execute(
                    "INSERT INTO knowledge_jobs "
                    "(job_type,processing_status,answer_request_id,question,"
                    "idempotency_key,created_by_actor_id) "
                    "VALUES ('answer','pending',LAST_INSERT_ID(),'legacy question',"
                    "'job:legacy','admin:legacy')"
                )
    finally:
        connection.close()


def _drop(config, *databases: str) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            for database in databases:
                assert database.startswith("lu_test_wp84_")
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


def _execute(config, database: str, statement: str) -> None:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
    finally:
        connection.close()


@pytest.mark.integration
# 保持完整生命週期在單一測試，證明 source→candidate receipts 彼此連續。
def test_empty_legacy_knowledge_rebuilds_only_on_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    container = os.environ["MYSQL_TEST_CONTAINER"]
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp84_source_{suffix}"
    candidate = f"lu_test_wp84_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_legacy_source(config, source, with_row=False)
        source_before = migration._schema_snapshot(config, source)["sha256"]
        plan = migration.build_plan(config, source, candidate, RECOVERABLE)
        assert plan["legacy_knowledge_empty_rebuild"]["eligible"] is True
        paths = {
            name: tmp_path / name
            for name in ("plan", "dump", "backup", "operation")
        }
        migration.write_receipt(paths["plan"], plan)
        migration.create_source_dump(
            config, source, paths["dump"], paths["backup"],
            mysql_container=container,
        )
        migration.restore_candidate(
            config, source, candidate, paths["dump"], paths["backup"],
            paths["operation"], mysql_container=container,
        )
        migration.apply_schema(
            config, source, candidate, paths["plan"], paths["operation"],
            mysql_container=container,
            allowed_partial_artifacts=RECOVERABLE,
        )
        migration.verify_candidate(config, source, candidate, paths["operation"])

        assert migration._schema_snapshot(config, source)["sha256"] == source_before
        assert migration._owned_classification(migration._schema_snapshot(config, candidate)) == {
            PART_148.name: "exact", PART_163.name: "exact",
        }
    finally:
        _drop(config, candidate, source)


@pytest.mark.integration
def test_nonempty_legacy_knowledge_is_blocked_during_read_only_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp84_nonempty_{suffix}"
    candidate = f"lu_test_wp84_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_legacy_source(config, source, with_row=True)
        source_before = migration._schema_snapshot(config, source)["sha256"]
        with pytest.raises(
            migration.UpgradeBlocked,
            match="legacy Knowledge tables are not empty",
        ):
            migration.build_plan(config, source, candidate, RECOVERABLE)
        assert migration._schema_snapshot(config, source)["sha256"] == source_before
    finally:
        _drop(config, candidate, source)


@pytest.mark.integration
def test_canonical_request_and_job_rows_survive_candidate_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    container = os.environ["MYSQL_TEST_CONTAINER"]
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp84_preserved_{suffix}"
    candidate = f"lu_test_wp84_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_legacy_source(
            config,
            source,
            with_row=False,
            with_request_job_rows=True,
        )
        plan = migration.build_plan(config, source, candidate, RECOVERABLE)
        assert plan["legacy_knowledge_empty_rebuild"]["eligible"] is True
        assert plan["legacy_knowledge_empty_rebuild"]["preserved_tables"] == [
            "knowledge_answer_requests",
            "knowledge_jobs",
        ]
        paths = {
            name: tmp_path / name
            for name in ("plan", "dump", "backup", "operation")
        }
        migration.write_receipt(paths["plan"], plan)
        migration.create_source_dump(
            config,
            source,
            paths["dump"],
            paths["backup"],
            mysql_container=container,
        )
        migration.restore_candidate(
            config,
            source,
            candidate,
            paths["dump"],
            paths["backup"],
            paths["operation"],
            mysql_container=container,
        )
        migration.apply_schema(
            config,
            source,
            candidate,
            paths["plan"],
            paths["operation"],
            mysql_container=container,
            allowed_partial_artifacts=RECOVERABLE,
        )
        migration.verify_candidate(config, source, candidate, paths["operation"])

        source_data = migration._table_evidence(config, source)
        candidate_data = migration._table_evidence(config, candidate)
        for table in ("knowledge_answer_requests", "knowledge_jobs"):
            assert candidate_data[table] == source_data[table]
    finally:
        _drop(config, candidate, source)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            "ALTER TABLE knowledge_items ADD COLUMN unexpected_value INT",
            "partial/drift owned objects",
        ),
        (
            "CREATE TABLE outside_knowledge_reference ("
            "id BIGINT PRIMARY KEY,item_id BIGINT UNSIGNED NOT NULL,"
            "CONSTRAINT fk_outside_knowledge_item FOREIGN KEY (item_id) "
            "REFERENCES knowledge_items(id)) ENGINE=InnoDB",
            "external inbound foreign keys",
        ),
    ),
)
def test_legacy_metadata_drift_and_external_references_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    config = _config()
    suffix = uuid.uuid4().hex[:10]
    source = f"lu_test_wp84_blocked_{suffix}"
    candidate = f"lu_test_wp84_candidate_{suffix}"
    _configure_release(monkeypatch)
    try:
        _create_legacy_source(config, source, with_row=False)
        _execute(config, source, mutation)
        source_before = migration._schema_snapshot(config, source)["sha256"]
        with pytest.raises(migration.UpgradeBlocked, match=message):
            migration.build_plan(config, source, candidate, RECOVERABLE)
        assert migration._schema_snapshot(config, source)["sha256"] == source_before
    finally:
        _drop(config, candidate, source)


_LEGACY_KNOWLEDGE_SQL = """
CREATE TABLE knowledge_items (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, source_identity VARCHAR(191) NOT NULL,
 title VARCHAR(500) NOT NULL, lifecycle_status ENUM('draft','reviewed','published','retired') NOT NULL DEFAULT 'draft',
 current_version INT UNSIGNED NOT NULL DEFAULT 1, source_digest CHAR(64) NOT NULL,
 source_uri VARCHAR(1000) NULL, created_by_actor_id VARCHAR(191) NOT NULL,
 created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_knowledge_source_identity (source_identity), INDEX idx_knowledge_lifecycle (lifecycle_status,id),
 CONSTRAINT chk_knowledge_source_digest CHECK (source_digest REGEXP '^[0-9a-f]{64}$')) ENGINE=InnoDB;
CREATE TABLE knowledge_item_versions (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, item_id BIGINT UNSIGNED NOT NULL,
 item_version INT UNSIGNED NOT NULL, content MEDIUMTEXT NOT NULL, source_digest CHAR(64) NOT NULL,
 event_type ENUM('ingested','reviewed','published','retired') NOT NULL, actor_id VARCHAR(191) NOT NULL,
 reason VARCHAR(500) NULL, idempotency_key VARCHAR(191) NOT NULL,
 recorded_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_knowledge_item_version (item_id,item_version), UNIQUE KEY uq_knowledge_version_key (idempotency_key),
 CONSTRAINT fk_knowledge_version_item FOREIGN KEY (item_id) REFERENCES knowledge_items(id) ON UPDATE RESTRICT ON DELETE RESTRICT) ENGINE=InnoDB;
CREATE TABLE knowledge_answer_requests (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, question VARCHAR(2000) NOT NULL, requester_line_user_id VARCHAR(191) NULL,
 request_status ENUM('pending','processing','answered','unsupported','failed') NOT NULL DEFAULT 'pending',
 idempotency_key VARCHAR(191) NOT NULL, correlation_id VARCHAR(191) NOT NULL,
 created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), completed_at_utc DATETIME(6) NULL,
 UNIQUE KEY uq_knowledge_answer_request_key (idempotency_key), INDEX idx_knowledge_answer_request_status (request_status,id)) ENGINE=InnoDB;
CREATE TABLE knowledge_jobs (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, job_type ENUM('index_build','answer') NOT NULL,
 processing_status ENUM('pending','processing','completed','retry_pending','failed') NOT NULL DEFAULT 'pending',
 answer_request_id BIGINT UNSIGNED NULL, target_index_version INT UNSIGNED NULL, question VARCHAR(2000) NULL,
 attempt_count INT UNSIGNED NOT NULL DEFAULT 0, max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
 available_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), lease_owner VARCHAR(191) NULL,
 lease_expires_at_utc DATETIME(6) NULL, last_error_code VARCHAR(191) NULL, idempotency_key VARCHAR(191) NOT NULL,
 created_by_actor_id VARCHAR(191) NOT NULL, created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), completed_at_utc DATETIME(6) NULL,
 UNIQUE KEY uq_knowledge_job_key (idempotency_key), INDEX idx_knowledge_job_claim (processing_status,available_at_utc,id),
 CONSTRAINT fk_knowledge_job_answer_request FOREIGN KEY (answer_request_id) REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT) ENGINE=InnoDB;
CREATE TABLE knowledge_indexes (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, index_version INT UNSIGNED NOT NULL,
 index_status ENUM('requested','building','ready','stale','failed') NOT NULL, content_set_digest CHAR(64) NULL,
 built_at_utc DATETIME(6) NULL, created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_knowledge_index_version (index_version), INDEX idx_knowledge_index_ready (index_status,index_version)) ENGINE=InnoDB;
CREATE TABLE knowledge_answer_receipts (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, answer_request_id BIGINT UNSIGNED NOT NULL, answer_text TEXT NOT NULL,
 index_version INT UNSIGNED NOT NULL, authoritative BOOLEAN NOT NULL DEFAULT FALSE, line_delivery_task_id BIGINT UNSIGNED NULL,
 answered_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), UNIQUE KEY uq_knowledge_answer_receipt_request (answer_request_id),
 CONSTRAINT fk_knowledge_answer_request FOREIGN KEY (answer_request_id) REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
 CONSTRAINT fk_knowledge_answer_delivery FOREIGN KEY (line_delivery_task_id) REFERENCES line_delivery_tasks(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
 CONSTRAINT chk_knowledge_answer_non_authoritative CHECK (authoritative=FALSE)) ENGINE=InnoDB;
CREATE TABLE knowledge_answer_sources (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, answer_receipt_id BIGINT UNSIGNED NOT NULL,
 source_identity VARCHAR(191) NOT NULL, source_version INT UNSIGNED NOT NULL, safe_excerpt VARCHAR(500) NOT NULL,
 citation_order INT UNSIGNED NOT NULL, UNIQUE KEY uq_knowledge_answer_source_order (answer_receipt_id,citation_order),
 CONSTRAINT fk_knowledge_answer_source_receipt FOREIGN KEY (answer_receipt_id) REFERENCES knowledge_answer_receipts(id) ON UPDATE RESTRICT ON DELETE RESTRICT) ENGINE=InnoDB;
CREATE TRIGGER trg_knowledge_item_versions_before_update BEFORE UPDATE ON knowledge_item_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be updated';
CREATE TRIGGER trg_knowledge_item_versions_before_delete BEFORE DELETE ON knowledge_item_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be deleted';
"""


_VERIFIER_SUPPORT_SQL = """
CREATE TABLE system_alerts (
 id INT AUTO_INCREMENT PRIMARY KEY, alert_code VARCHAR(50) NOT NULL,
 source_domain VARCHAR(50) NOT NULL, case_key VARCHAR(100) NOT NULL,
 reason VARCHAR(500) NOT NULL, details JSON NOT NULL,
 status ENUM('open','claimed','resolved') NOT NULL DEFAULT 'open',
 claimed_by VARCHAR(100) NULL, claimed_at DATETIME NULL,
 resolved_by VARCHAR(100) NULL, resolved_at DATETIME NULL,
 resolution_reason VARCHAR(500) NULL,
 created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 UNIQUE KEY uq_alert_case (alert_code,case_key),
 KEY idx_system_alert_status (status)
) ENGINE=InnoDB;
CREATE TABLE orders (
 case_no VARCHAR(64) PRIMARY KEY, lifecycle_version BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB;
CREATE VIEW v_order_details AS
 SELECT case_no,lifecycle_version FROM orders;
"""
