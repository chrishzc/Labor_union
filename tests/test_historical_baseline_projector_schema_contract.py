"""
File: test_historical_baseline_projector_schema_contract.py
Description: 驗證 1011 歷史基準 projector 的 schema、release、descriptor 與組裝順序。
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
SQL_PATH = ROOT / "db/schema_parts/1011_historical_baseline_projector.sql"
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_28_historical_baseline_projector_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_28_historical_baseline_projector_v1.descriptors.json"
)

TABLES = {
    "historical_baseline_occurrences",
    "historical_baseline_umbrella_memberships",
    "historical_baseline_successors",
    "historical_baseline_projector_receipts",
}


def test_release_is_schema_only_hash_locked_and_follows_1010() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-historical-baseline-projector-2026-08-28-v1"
    )
    assert manifest["artifacts"] == [{
        "name": SQL_PATH.name,
        "relative_path": "db/schema_parts/1011_historical_baseline_projector.sql",
        "sha256": hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": (
            "forward-only-preserve-historical-baseline-projector-evidence"
        ),
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    release_index = migration.DEFAULT_RELEASE_MANIFESTS.index(MANIFEST_PATH.name)
    assert migration.DEFAULT_RELEASE_MANIFESTS[release_index - 1] == (
        "labor_union_2026_08_28_historical_operational_baseline_v1.json"
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


def test_fresh_assembly_orders_1011_before_1012() -> None:
    assembly = load_schema_assembly()

    names = [path.name for path in assembly.active_artifact_paths]
    assert names.index("1011_historical_baseline_projector.sql") < names.index(
        "1012_service_before_replacement.sql"
    )
    assert names[-1] == "1021_task96_owner_contract_successors.sql"


def _table_block(sql: str, table: str) -> str:
    prefix = f"CREATE TABLE IF NOT EXISTS {table} ("
    start = sql.index(prefix) + len(prefix)
    depth = 1
    for offset, character in enumerate(sql[start:], start=start):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return sql[start:offset]
    raise AssertionError(f"unterminated CREATE TABLE for {table}")


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _assert_projector_contract(sql: str) -> None:
    created_tables = set(
        re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z0-9_]+)\s*\(", sql)
    )
    assert created_tables == TABLES

    occurrence = _table_block(sql, "historical_baseline_occurrences")
    for column in (
        "occurrence_identity",
        "case_no",
        "order_identity",
        "baseline_event_id",
        "baseline_receipt_id",
        "catalog_identity",
        "catalog_version",
        "descriptor_identity",
        "contract_id",
        "contract_version",
        "step_number",
        "owner_domain",
        "root_identity_kind",
        "root_identity_path",
        "terminal_predicate_id",
        "terminal_predicate_version",
        "repair_target",
        "repair_capability",
        "observation_variant",
        "observation_identity",
        "observed_root_identity",
        "owner_source_event_identity",
        "owner_source_version",
        "terminal_result",
        "unavailable_code",
        "owner_binding_fingerprint",
    ):
        assert re.search(rf"^\s*{column}\s", occurrence, re.MULTILINE)
    assert "UNIQUE KEY uq_hbp_occurrence_identity" in occurrence
    assert "UNIQUE KEY uq_hbp_occurrence_observation" in occurrence
    assert "UNIQUE KEY uq_hbp_occurrence_membership_lineage" in occurrence
    assert "UNIQUE KEY uq_hbp_occurrence_successor_lineage" in occurrence
    assert "REFERENCES orders(case_no)" in occurrence
    assert "REFERENCES historical_order_operational_baseline_events(id)" in occurrence
    assert "REFERENCES historical_order_operational_baseline_receipts(id)" in occurrence
    assert "observation_variant = 'available'" in occurrence
    assert "observation_variant = 'unavailable'" in occurrence
    assert "observed_root_identity IS NULL" in occurrence
    assert "owner_source_version IS NULL" in occurrence
    assert "unavailable_code IS NULL" in occurrence
    assert sql.count("receipt.event_id = event.id") == 2
    assert sql.count("event.case_no = NEW.case_no") == 2
    assert sql.count("event.order_identity = NEW.order_identity") == 2

    membership = _table_block(sql, "historical_baseline_umbrella_memberships")
    for column in (
        "membership_identity",
        "umbrella_identity",
        "projector_receipt_id",
        "set_ordinal",
        "occurrence_id",
        "anomaly_alert_fingerprint",
        "case_no",
        "order_identity",
        "baseline_event_id",
        "catalog_identity",
        "catalog_version",
    ):
        assert re.search(rf"^\s*{column}\s", membership, re.MULTILINE)
    assert "UNIQUE KEY uq_hbp_membership_occurrence" in membership
    assert "UNIQUE KEY uq_hbp_membership_receipt_ordinal" in membership
    assert "REFERENCES anomaly_current_alerts(fingerprint)" in membership
    compact_membership = _compact(membership)
    assert (
        "FOREIGN KEY ( occurrence_id, case_no, order_identity, baseline_event_id, "
        "catalog_identity, catalog_version ) REFERENCES "
        "historical_baseline_occurrences ( id, case_no, order_identity, "
        "baseline_event_id, catalog_identity, catalog_version )"
    ) in compact_membership
    assert (
        "FOREIGN KEY ( projector_receipt_id, case_no, order_identity, "
        "baseline_event_id, catalog_identity, catalog_version, umbrella_identity ) "
        "REFERENCES historical_baseline_projector_receipts ( id, case_no, "
        "order_identity, baseline_event_id, catalog_identity, catalog_version, "
        "umbrella_identity )"
    ) in compact_membership
    assert "set_ordinal > 0" in membership
    assert "alert.source_identity = NEW.umbrella_identity" in sql

    successor = _table_block(sql, "historical_baseline_successors")
    for column in (
        "successor_relation_identity",
        "predecessor_occurrence_id",
        "successor_occurrence_id",
        "case_no",
        "order_identity",
        "baseline_event_id",
        "catalog_identity",
        "catalog_version",
        "descriptor_identity",
        "contract_id",
        "contract_version",
        "owner_event_identity",
        "prior_owner_source_version",
        "new_owner_source_version",
        "terminal_predicate_id",
        "terminal_predicate_version",
        "fresh_readback_fingerprint",
    ):
        assert re.search(rf"^\s*{column}\s", successor, re.MULTILINE)
    assert "UNIQUE KEY uq_hbp_successor_predecessor" in successor
    compact_successor = _compact(successor)
    shared_lineage = (
        "case_no, order_identity, baseline_event_id, catalog_identity, "
        "catalog_version, descriptor_identity, contract_id, contract_version, "
        "terminal_predicate_id, terminal_predicate_version"
    )
    assert (
        "FOREIGN KEY ( predecessor_occurrence_id, "
        f"{shared_lineage}, prior_owner_source_version ) REFERENCES "
        "historical_baseline_occurrences ( id, "
        f"{shared_lineage}, owner_source_version )"
    ) in compact_successor
    assert (
        "FOREIGN KEY ( successor_occurrence_id, "
        f"{shared_lineage}, new_owner_source_version ) REFERENCES "
        "historical_baseline_occurrences ( id, "
        f"{shared_lineage}, owner_source_version )"
    ) in compact_successor
    assert "new_owner_source_version > prior_owner_source_version" in successor
    assert "predecessor_occurrence_id <> successor_occurrence_id" in successor

    receipt = _table_block(sql, "historical_baseline_projector_receipts")
    for column in (
        "projector_receipt_identity",
        "source_intent_key",
        "payload_digest",
        "idempotency_key",
        "baseline_event_id",
        "baseline_receipt_id",
        "baseline_outbox_id",
        "case_no",
        "order_identity",
        "catalog_identity",
        "catalog_version",
        "whole_vector_fingerprint",
        "whole_vector_count",
        "occurrence_set_digest",
        "occurrence_set_count",
        "umbrella_identity",
        "result_state",
        "post_commit_readback_digest",
    ):
        assert re.search(rf"^\s*{column}\s", receipt, re.MULTILINE)
    for unique_key in (
        "uq_hbp_projector_receipt_identity",
        "uq_hbp_projector_source_intent",
        "uq_hbp_projector_idempotency",
    ):
        assert f"UNIQUE KEY {unique_key}" in receipt
    assert "REFERENCES historical_order_operational_baseline_events(id)" in receipt
    assert "REFERENCES historical_order_operational_baseline_receipts(id)" in receipt
    assert "REFERENCES historical_order_operational_baseline_outbox(id)" in receipt
    assert "REFERENCES orders(case_no)" in receipt
    assert "UNIQUE KEY uq_hbp_projector_membership_lineage" in receipt
    assert "outbox.event_id = event.id" in sql
    assert "outbox.receipt_id = receipt.id" in sql
    assert "outbox.intent_key = NEW.source_intent_key" in sql
    assert "whole_vector_count > 0" in receipt
    assert "occurrence_set_count >= 0" in receipt

    for table in TABLES:
        assert f"BEFORE UPDATE ON {table}" in sql
        assert f"{table} records cannot be updated" in sql
        assert f"BEFORE DELETE ON {table}" in sql
        assert f"{table} records cannot be deleted" in sql

    assert not re.search(
        r"^\s*(?:INSERT\s+INTO|UPDATE\s+[a-z0-9_]+\s+SET|DELETE\s+FROM)\b",
        sql,
        re.IGNORECASE | re.MULTILINE,
    )
    assert not re.search(r"\bALTER\s+TABLE\b", sql, re.I)
    assert not re.search(r"\bDROP\s+TABLE\b", sql, re.I)


def test_schema_defines_the_complete_immutable_projector_contract() -> None:
    _assert_projector_contract(SQL_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("required_fragment", "replacement"),
    (
        ("new_owner_source_version > prior_owner_source_version", "1 = 1"),
        ("receipt.event_id = event.id", "receipt.event_id = receipt.event_id"),
        ("event.case_no = NEW.case_no", "event.case_no = event.case_no"),
        ("outbox.intent_key = NEW.source_intent_key", "outbox.intent_key = outbox.intent_key"),
        ("alert.source_identity = NEW.umbrella_identity", "alert.source_identity = alert.source_identity"),
        (
            "catalog_version,\n            umbrella_identity\n        ) REFERENCES historical_baseline_projector_receipts",
            "catalog_version,\n            baseline_event_id\n        ) REFERENCES historical_baseline_projector_receipts",
        ),
        (
            "predecessor_occurrence_id,\n            case_no,\n            order_identity,\n            baseline_event_id,\n            catalog_identity,\n            catalog_version,\n            descriptor_identity,",
            "predecessor_occurrence_id,\n            case_no,\n            order_identity,\n            baseline_event_id,\n            catalog_identity,\n            catalog_version,",
        ),
        ("observation_variant = 'unavailable'", "observation_variant = 'available'"),
    ),
)
def test_contract_checker_rejects_known_bad_schema(
    required_fragment: str,
    replacement: str,
) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    assert required_fragment in sql

    with pytest.raises(AssertionError):
        _assert_projector_contract(sql.replace(required_fragment, replacement, 1))
