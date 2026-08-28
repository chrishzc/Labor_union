"""
File: test_service_before_replacement_schema_contract.py
Description: 驗證 1012 服務前換人的 schema、release、descriptor 與組裝終點。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1012_service_before_replacement.sql"
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_28_service_before_replacement_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_28_service_before_replacement_v1.descriptors.json"
)
TABLES = {
    "scheduling_service_before_replacement_events",
    "scheduling_service_before_replacement_roots",
    "scheduling_service_before_replacement_successors",
    "scheduling_service_before_replacement_receipts",
    "scheduling_service_before_replacement_outbox",
}


def test_release_is_schema_only_hash_locked_and_follows_1011() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-service-before-replacement-2026-08-28-v1"
    )
    assert manifest["artifacts"] == [{
        "name": SQL_PATH.name,
        "relative_path": "db/schema_parts/1012_service_before_replacement.sql",
        "sha256": hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": (
            "forward-only-preserve-service-before-replacement-evidence"
        ),
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    release_index = migration.DEFAULT_RELEASE_MANIFESTS.index(MANIFEST_PATH.name)
    assert migration.DEFAULT_RELEASE_MANIFESTS[release_index - 1] == (
        "labor_union_2026_08_28_historical_baseline_projector_v1.json"
    )
    loaded = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert loaded.schema_paths(ROOT) == (SQL_PATH.resolve(),)


def test_descriptor_matches_every_canonical_owned_object() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH,
        ROOT,
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert set(released["tables"]) == TABLES
    assert released["tables"] == {
        table: set(columns)
        for table, columns in canonical["tables"].items()
    }
    for kind in ("indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])
    assert canonical["parent_columns"] == {}


def test_fresh_assembly_ends_at_1012() -> None:
    assembly = load_schema_assembly()

    assert [path.name for path in assembly.active_artifact_paths[-3:]] == [
        "1010_historical_operational_baseline.sql",
        "1011_historical_baseline_projector.sql",
        "1012_service_before_replacement.sql",
    ]


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def _assert_fresh_zero_service_guard(sql: str) -> None:
    assert "AND NOT EXISTS (" in sql
    assert "FROM scheduling_service_day_logs AS service_day_log" in sql
    assert "service_day_log.case_no = NEW.case_no" in sql


def test_schema_is_additive_and_has_only_the_five_owner_records() -> None:
    sql = _sql()

    assert set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z0-9_]+)", sql)) == TABLES
    for forbidden_statement in (
        r"(?im)^\s*ALTER\s+TABLE\b",
        r"(?im)^\s*DROP\s+TABLE\b",
        r"(?im)^\s*TRUNCATE\b",
        r"(?im)^\s*INSERT\s+INTO\b",
        r"(?im)^\s*REPLACE\s+INTO\b",
        r"(?im)^\s*UPDATE\s+[a-z0-9_]",
        r"(?im)^\s*DELETE\s+FROM\b",
    ):
        assert re.search(forbidden_statement, sql) is None
    assert "CREATE VIEW" not in sql


def test_event_binds_case_generations_strict_versions_and_zero_service_proof() -> None:
    sql = _sql()

    for column in (
        "replacement_event_identity VARCHAR(191) NOT NULL",
        "prior_replacement_event_id BIGINT UNSIGNED NULL",
        "case_no VARCHAR(50) NOT NULL",
        "prior_generation_id BIGINT NOT NULL",
        "replacement_generation_id BIGINT NOT NULL",
        "prior_generation_identity VARCHAR(191) NOT NULL",
        "replacement_generation_identity VARCHAR(191) NOT NULL",
        "prior_event_identity VARCHAR(191) NOT NULL",
        "expected_aggregate_version BIGINT UNSIGNED NOT NULL",
        "resulting_aggregate_version BIGINT UNSIGNED NOT NULL",
        "expected_generation_version BIGINT UNSIGNED NOT NULL",
        "resulting_generation_version BIGINT UNSIGNED NOT NULL",
        "expected_event_version BIGINT UNSIGNED NOT NULL",
        "resulting_event_version BIGINT UNSIGNED NOT NULL",
        "zero_service_proof_identity VARCHAR(191) NOT NULL",
        "zero_service_proof_contract_version SMALLINT UNSIGNED NOT NULL",
        "zero_service_source_projection_identity VARCHAR(191) NOT NULL",
        "zero_service_source_projection_version BIGINT UNSIGNED NOT NULL",
        "zero_service_proof_version BIGINT UNSIGNED NOT NULL",
        "official_service_day_count INT UNSIGNED NOT NULL",
        "replacement_reason VARCHAR(500) NOT NULL",
        "actor_id VARCHAR(191) NOT NULL",
        "capability_atom VARCHAR(191) NOT NULL",
        "idempotency_key VARCHAR(191) NOT NULL",
    ):
        assert column in sql
    assert "REFERENCES orders(case_no)" in sql
    assert sql.count("REFERENCES scheduling_generations(id, case_no)") == 2
    assert "REFERENCES scheduling_service_before_replacement_events(\n            id," in sql
    assert "UNIQUE KEY uq_service_before_replacement_event_prior" in sql
    assert "prior_replacement_event_id,\n            case_no,\n            expected_aggregate_version,\n            expected_generation_version,\n            expected_event_version" in sql
    assert "id,\n            case_no,\n            resulting_aggregate_version,\n            resulting_generation_version,\n            resulting_event_version" in sql
    assert "resulting_aggregate_version > expected_aggregate_version" in sql
    assert "resulting_generation_version > expected_generation_version" in sql
    assert "resulting_event_version > expected_event_version" in sql
    assert "official_service_day_count = 0" in sql
    assert "'scheduling_official_service_projection'" in sql
    assert "zero_service_proof_contract_version = 1" in sql
    assert "zero_service_source_projection_version = zero_service_proof_version" in sql
    for digest in (
        "zero_service_proof_fingerprint",
        "reason_evidence_digest",
        "command_fingerprint",
        "preview_fingerprint",
    ):
        assert f"{digest} REGEXP '^[0-9a-f]{{64}}$'" in sql
    assert "prior_generation.generation_number = NEW.expected_generation_version" in sql
    assert "replacement_generation.generation_number = NEW.resulting_generation_version" in sql
    assert "aggregate.aggregate_version = NEW.resulting_aggregate_version" in sql
    assert "aggregate.generation_counter = NEW.resulting_generation_version" in sql
    assert "aggregate.effective_generation_id = NEW.replacement_generation_id" not in sql
    _assert_fresh_zero_service_guard(sql)


def test_zero_service_guard_negative_control_detects_a_missing_absence_check() -> None:
    sql = _sql()

    _assert_fresh_zero_service_guard(sql)
    without_absence_guard = sql.replace("AND NOT EXISTS (", "AND EXISTS (", 1)
    with pytest.raises(AssertionError):
        _assert_fresh_zero_service_guard(without_absence_guard)


def test_root_relations_are_exact_relational_sets_without_json_shortcut() -> None:
    sql = _sql()
    root_table = sql.split(
        "CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_roots (",
        maxsplit=1,
    )[1].split(") ENGINE=InnoDB", maxsplit=1)[0]

    assert "root_identity VARCHAR(191) NOT NULL" in root_table
    assert "owner_domain ENUM('scheduling', 'matching') NOT NULL" in root_table
    assert "disposition ENUM('retained', 'superseded', 'created') NOT NULL" in root_table
    assert "canonical_ordinal INT UNSIGNED NOT NULL" in root_table
    assert "UNIQUE KEY uq_service_before_replacement_root_identity" in root_table
    assert "replacement_event_id,\n        root_identity" in root_table
    assert "UNIQUE KEY uq_service_before_replacement_root_ordinal" in root_table
    assert "canonical_ordinal > 0" in root_table
    assert "owner_descriptor_identity VARCHAR(191) NOT NULL" in root_table
    assert "owner_descriptor_version BIGINT UNSIGNED NOT NULL" in root_table
    assert "owner_descriptor_fingerprint CHAR(64)" in root_table
    assert "owner_descriptor_version > 0" in root_table
    assert "owner_descriptor_fingerprint REGEXP '^[0-9a-f]{64}$'" in root_table
    assert "owner_domain = 'matching'" in root_table
    assert "owner_domain = 'scheduling'" in root_table
    assert "root_identity NOT REGEXP '[[:cntrl:]]'" in root_table
    assert " JSON " not in root_table


def test_successor_is_bound_to_owner_event_generation_and_matching_facts() -> None:
    sql = _sql()

    assert "FOREIGN KEY (\n            replacement_event_id,\n            case_no,\n            replacement_generation_id,\n            scenario" in sql
    assert "REFERENCES matching_coordination_package_lineage(id)" in sql
    assert "REFERENCES matching_coordination_events(id)" in sql
    assert "matching_package.package_id = NEW.successor_package_identity" in sql
    assert "matching_event.event_id = NEW.successor_matching_event_identity" in sql
    assert "matching_package.case_no = NEW.case_no" in sql
    assert "matching_event.case_no = NEW.case_no" in sql
    assert "UNIQUE KEY uq_service_before_replacement_successor_event" in sql
    assert "UNIQUE KEY uq_service_before_replacement_successor_round" in sql
    assert "scenario = 'R-07'" in sql
    assert "candidate_count = 0" in sql
    assert "zero_candidate_disposition = 'blocked_no_candidate'" in sql
    assert "reuse_proof_variant ENUM('not_reused', 'candidate_pool_reused') NOT NULL" in sql
    for reuse_column in (
        "reuse_pool_identity VARCHAR(191) NULL",
        "reuse_round_identity VARCHAR(191) NULL",
        "reuse_coverage_version BIGINT UNSIGNED NULL",
        "reuse_availability_version BIGINT UNSIGNED NULL",
        "reuse_willingness_version BIGINT UNSIGNED NULL",
        "reuse_candidate_identity VARCHAR(191) NULL",
        "reuse_proof_fingerprint CHAR(64)",
    ):
        assert reuse_column in sql
    assert "reuse_round_identity = successor_round_identity" in sql
    assert "reuse_proof_variant = 'not_reused'" in sql
    assert "reuse_proof_variant = 'candidate_pool_reused'" in sql
    assert "reuse_accepted_candidate = 0" in sql
    assert "reuse_accepted_candidate = 1" in sql
    assert "resume_step = 'step_2'" in sql
    assert "resume_step = 'step_3'" in sql
    assert "resume_step = 'step_4'" in sql


def test_receipt_keeps_three_recomputable_root_set_digests_and_exact_binding() -> None:
    sql = _sql()

    for disposition in ("retained", "superseded", "created"):
        assert f"{disposition}_root_set_digest CHAR(64)" in sql
        assert f"{disposition}_root_count INT UNSIGNED NOT NULL" in sql
        assert f"{disposition}_root_set_digest REGEXP '^[0-9a-f]{{64}}$'" in sql
    assert "UNIQUE KEY uq_service_before_replacement_receipt_idempotency" in sql
    assert "UNIQUE KEY uq_service_before_replacement_receipt_outbox" in sql
    assert "FOREIGN KEY (successor_binding_id, replacement_event_id, case_no)" in sql
    assert "resulting_aggregate_version,\n            resulting_generation_version,\n            resulting_event_version" in sql
    receipt_table = sql.split(
        "CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_receipts (",
        maxsplit=1,
    )[1].split(") ENGINE=InnoDB", maxsplit=1)[0]
    assert "root_ids" not in receipt_table
    assert "JSON" not in receipt_table
    assert "root_set_digest_contract ENUM('sha256_newline_v1') NOT NULL" in receipt_table
    assert "trg_service_before_replacement_receipts_before_insert" in sql
    for disposition in ("retained", "superseded", "created"):
        assert f"{disposition}_root.disposition = '{disposition}'" in sql
        assert f"MAX({disposition}_root.canonical_ordinal)" in sql
    assert "GROUP_CONCAT" not in sql
    receipt_trigger = sql.split(
        "CREATE TRIGGER trg_service_before_replacement_receipts_before_insert",
        maxsplit=1,
    )[1].split(
        "CREATE TRIGGER trg_service_before_replacement_receipts_before_update",
        maxsplit=1,
    )[0]
    for disposition in ("retained", "superseded", "created"):
        assert f"NEW.{disposition}_root_set_digest =" not in receipt_trigger


def test_outbox_has_one_internal_projection_intent_and_no_external_effect() -> None:
    sql = _sql()
    outbox_table = sql.split(
        "CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_outbox (",
        maxsplit=1,
    )[1].split(") ENGINE=InnoDB", maxsplit=1)[0]

    assert "intent_type ENUM('successor_projection_readback_requested') NOT NULL" in outbox_table
    assert "target_owner ENUM('orders_anomalies_projection') NOT NULL" in outbox_table
    assert "UNIQUE KEY uq_service_before_replacement_outbox_event" in outbox_table
    assert "UNIQUE KEY uq_service_before_replacement_outbox_receipt" in outbox_table
    assert "bounded_payload JSON NOT NULL" in outbox_table
    assert "receipt.outbox_identity = NEW.outbox_identity" in sql
    for forbidden_target in ("line_integration", "payment", "payroll"):
        assert forbidden_target not in outbox_table


def test_event_roots_successor_receipt_are_immutable_and_outbox_only_updates_delivery() -> None:
    sql = _sql()

    for table in (
        "scheduling_service_before_replacement_events",
        "scheduling_service_before_replacement_roots",
        "scheduling_service_before_replacement_successors",
        "scheduling_service_before_replacement_receipts",
    ):
        assert f"{table} records cannot be updated" in sql
        assert f"{table} records cannot be deleted" in sql
    assert "trg_service_before_replacement_outbox_before_update" in sql
    assert "scheduling_service_before_replacement_outbox records cannot be deleted" in sql
    for business_column in (
        "id",
        "replacement_event_id",
        "receipt_id",
        "case_no",
        "outbox_identity",
        "intent_type",
        "target_owner",
        "bounded_payload",
        "created_at",
    ):
        assert f"OLD.{business_column} <=> NEW.{business_column}" in sql
    for delivery_column in ("published_at", "attempts", "last_error"):
        assert f"OLD.{delivery_column} <=> NEW.{delivery_column}" not in sql
