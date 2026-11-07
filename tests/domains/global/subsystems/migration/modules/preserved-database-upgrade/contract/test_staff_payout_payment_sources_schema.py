"""Static release/metadata checks only: no cursor, SQL execution or DB connection."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.build_validation_schema_release import verify_release
from scripts.compact_fresh_schema import load_compact_plan
from scripts.schema_assembly import validate_schema_assembly
from scripts.verify_validation_schema_manifest import load_manifest
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1070_staff_payout_payment_sources.sql"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_11_06_staff_payout_payment_sources_v1.json"
TABLE = "staff_payout_events"
CHECK = (TABLE, "chk_staff_payout_payment_source")


def _snapshot(descriptor):
    """Plain metadata input for the existing comparator; no SQL driver is involved."""
    return {
        "columns": [
            {"table_name": table, "column_name": name, **contract}
            for table, columns in {
                **descriptor["tables"], **descriptor["parent_columns"],
            }.items()
            for name, contract in columns.items()
        ],
        "indexes": [
            {"table_name": table, "index_name": name,
             "non_unique": contract["non_unique"], "columns": ",".join(contract["columns"])}
            for (table, name), contract in descriptor["indexes"].items()
        ],
        "constraints": [
            {"table_name": table, "constraint_name": name,
             "constraint_type": "CHECK", "enforced": "YES", "check_clause": clause}
            for (table, name), clause in descriptor["checks"].items()
        ] + [
            {"table_name": table, "constraint_name": name, "constraint_type": "FOREIGN KEY"}
            for table, name in descriptor["foreign_keys"]
        ],
        "key_columns": [
            {"table_name": table, "constraint_name": name, "column_name": column,
             "referenced_table_name": contract["referenced_table"],
             "referenced_column_name": referenced}
            for (table, name), contract in descriptor["foreign_keys"].items()
            for column, referenced in zip(contract["columns"], contract["referenced_columns"])
        ],
        "foreign_keys": [
            {"table_name": table, "constraint_name": name,
             "update_rule": contract["update_rule"], "delete_rule": contract["delete_rule"]}
            for (table, name), contract in descriptor["foreign_keys"].items()
        ],
        "triggers": [
            {"trigger_name": name, **contract}
            for name, contract in descriptor["triggers"].items()
        ],
        "show_create_tables": {}, "views": [],
    }


def test_successor_is_current_hash_bound_and_schema_only():
    release = load_migration_release_manifest(MANIFEST, ROOT)
    descriptor = release.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert MANIFEST.name in migration.DEFAULT_RELEASE_MANIFESTS
    assert release.release_id in {item.release_id for item in migration.RELEASE_MANIFEST.manifests}
    assert {key: value for key, value in descriptor.items() if key != "triggers"} == {
        key: value for key, value in canonical.items() if key != "triggers"
    }
    assert descriptor["triggers"] == set(canonical["triggers"])
    assert release.backfills == ()
    assert {name: descriptor["parent_columns"][TABLE][name]
            for name in ("bank_account_identity_hash", "payment_source_kind")} == {
        "bank_account_identity_hash": {
            "column_type": "char(64)", "is_nullable": "YES", "column_default": None, "extra": "",
        },
        "payment_source_kind": {
            "column_type": "enum('legacy_unspecified','bank_statement','manual_supplement')",
            "is_nullable": "NO", "column_default": "legacy_unspecified", "extra": "",
        },
    }
    assert len(descriptor["parent_columns"][TABLE]) == 14
    assert len(descriptor["indexes"]) == 4
    assert len(descriptor["foreign_keys"]) == 3
    assert len(descriptor["checks"]) == 4
    assert descriptor["triggers"] == {
        "trg_staff_payout_events_before_update", "trg_staff_payout_events_before_delete",
    }
    statement, = migration.split_sql((ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8"))
    assert migration._local_classify_statement(statement) == "staff_payout_payment_source_widen"
    with pytest.raises(migration.LocalAdditiveBlocked, match="destructive ALTER"):
        migration._local_classify_statement(statement.replace("CHAR(64) NULL", "CHAR(64) NOT NULL"))
    assert statement.upper().count("DROP CHECK") == 1
    assert "DROP CHECK chk_staff_payout_account_hash" in statement
    assert "DROP COLUMN" not in statement.upper()
    assert "DROP TABLE" not in statement.upper()
    original = migration._canonical_artifact_descriptor("114_staff_payout_ledger.sql")
    check_start = statement.index("ADD CONSTRAINT chk_staff_payout_account_hash")
    opening = statement.index("CHECK (", check_start) + len("CHECK ")
    restored, _ = migration._extract_parenthesized(statement, opening)
    assert migration._normalize_check_contract(restored) == migration._normalize_check_contract(
        original["checks"][(TABLE, "chk_staff_payout_account_hash")]
    )
    with pytest.raises(migration.LocalAdditiveBlocked, match="destructive ALTER"):
        migration._local_classify_statement(statement.replace(
            "    DROP CHECK chk_staff_payout_account_hash,\n", ""
        ))
    assert "finance_import_row_id" not in statement


def test_current_fresh_assembly_full_and_compact_share_the_source_contract():
    assert validate_schema_assembly() == []
    assert verify_release(load_manifest()) == []
    plan = load_compact_plan()
    event_sql, = (step["sql"] for step in plan["steps"]
                  if step["sql"].startswith("CREATE TABLE `staff_payout_events`"))
    assert "`bank_account_identity_hash` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL" in event_sql
    assert "DEFAULT 'legacy_unspecified'" in event_sql
    checks = migration._show_create_check_clauses(event_sql)
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert migration._normalize_check_contract(checks[CHECK]) == migration._normalize_check_contract(canonical["checks"][CHECK])
    original = migration._canonical_artifact_descriptor("114_staff_payout_ledger.sql")
    original_hash = (TABLE, "chk_staff_payout_account_hash")
    assert migration._normalize_check_contract(checks[original_hash]) == migration._normalize_check_contract(original["checks"][original_hash])


def test_metadata_accepts_only_exact_predecessor_or_complete_successor():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    successor = _snapshot(descriptor)
    assert migration.local_additive_descriptor_state(successor, descriptor, ARTIFACT) == "exact"
    predecessor = deepcopy(successor)
    predecessor["columns"] = [row for row in predecessor["columns"] if row["column_name"] != "payment_source_kind"]
    next(row for row in predecessor["columns"] if row["column_name"] == "bank_account_identity_hash")["is_nullable"] = "NO"
    predecessor["constraints"] = [row for row in predecessor["constraints"] if row["constraint_name"] != CHECK[1]]
    assert migration.local_additive_descriptor_state(predecessor, descriptor, ARTIFACT) == "absent"
    half_applied = deepcopy(successor)
    half_applied["constraints"] = [row for row in half_applied["constraints"] if row["constraint_name"] != CHECK[1]]
    assert migration.local_additive_descriptor_state(half_applied, descriptor, ARTIFACT) == "partial"
    for change in ("nullable_source", "missing_legacy", "bank_default", "invalid_check", "disabled_check"):
        drift = deepcopy(successor)
        source = next(row for row in drift["columns"] if row["column_name"] == "payment_source_kind")
        source_check = next(row for row in drift["constraints"] if row["constraint_name"] == CHECK[1])
        if change == "nullable_source":
            source["is_nullable"] = "YES"
        elif change == "missing_legacy":
            source["column_type"] = "enum('bank_statement','manual_supplement')"
        elif change == "bank_default":
            source["column_default"] = "bank_statement"
        elif change == "disabled_check":
            source_check["enforced"] = "NO"
        else:
            source_check["check_clause"] = "bank_account_identity_hash IS NULL"
        assert migration.local_additive_descriptor_state(drift, descriptor, ARTIFACT) == "drift"
    half_applied = deepcopy(successor)
    next(row for row in half_applied["columns"] if row["column_name"] == "bank_account_identity_hash")["is_nullable"] = "NO"
    assert migration.local_additive_descriptor_state(half_applied, descriptor, ARTIFACT) == "drift"


def test_historical_ledger_accepts_selected_successor_and_keeps_original_guards():
    original = migration._canonical_artifact_descriptor("114_staff_payout_ledger.sql")
    predecessor = _snapshot(original)
    assert migration._canonical_artifact_metadata_state(predecessor, "114_staff_payout_ledger.sql") == "exact"
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    current = deepcopy(predecessor)
    changed = successor["parent_columns"][TABLE]
    for row in current["columns"]:
        if row["table_name"] == TABLE and row["column_name"] in changed:
            row.update(changed[row["column_name"]])
    current["columns"].append({"table_name": TABLE, "column_name": "payment_source_kind", **changed["payment_source_kind"]})
    current["constraints"].append(next(row for row in _snapshot(successor)["constraints"] if row["constraint_name"] == CHECK[1]))
    assert migration.local_additive_descriptor_state(current, successor, ARTIFACT) == "exact"
    states = migration._owned_classification(current)
    assert states["114_staff_payout_ledger.sql"] == states[ARTIFACT] == "exact"
    for missing in ("chk_staff_payout_account_hash", "chk_staff_payout_payment_source"):
        damaged = deepcopy(current)
        damaged["constraints"] = [row for row in damaged["constraints"] if row["constraint_name"] != missing]
        assert migration.local_additive_descriptor_state(damaged, successor, ARTIFACT) in {"partial", "drift"}
    damaged = deepcopy(current)
    damaged["triggers"] = [row for row in damaged["triggers"] if row["trigger_name"] != "trg_staff_payout_events_before_update"]
    assert migration.local_additive_descriptor_state(damaged, successor, ARTIFACT) == "partial"
    damaged = deepcopy(current)
    next(row for row in damaged["triggers"] if row["trigger_name"] == "trg_staff_payout_events_before_update")["action_statement"] = "BEGIN SET @unexpected=1; END"
    assert migration.local_additive_descriptor_state(damaged, successor, ARTIFACT) == "drift"
    damaged = deepcopy(current)
    damaged["triggers"].append({**damaged["triggers"][0], "trigger_name": "unexpected_payout_guard"})
    assert migration.local_additive_descriptor_state(damaged, successor, ARTIFACT) == "drift"
    for key in ("columns", "indexes", "foreign_keys"):
        damaged = deepcopy(current)
        if key == "columns":
            next(row for row in damaged[key] if row["table_name"] == TABLE and row["column_name"] == "amount_ntd")["column_type"] = "int"
        elif key == "indexes":
            next(row for row in damaged[key] if row["table_name"] == TABLE and row["index_name"] == "uq_staff_payout_import_row")["non_unique"] = 1
        else:
            next(row for row in damaged[key] if row["table_name"] == TABLE and row["constraint_name"] == "fk_staff_payout_staff")["delete_rule"] = "CASCADE"
        assert migration.local_additive_descriptor_state(damaged, successor, ARTIFACT) == "drift"


def test_parent_guard_metadata_does_not_claim_other_parent_guards():
    """Synthetic metadata exercises the generic comparator, not the 1060 special route."""
    guard = {
        "action_timing": "BEFORE", "event_manipulation": "DELETE",
        "event_object_table": "example_parent",
        "action_statement": migration._normalize_sql_contract(
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='immutable'"
        ),
    }
    descriptor = {
        "tables": {}, "parent_columns": {"example_parent": {
            "id": {"column_type": "bigint", "is_nullable": "NO", "column_default": None, "extra": ""},
        }}, "indexes": {}, "foreign_keys": {}, "checks": {},
        "triggers": {"declared_parent_delete": guard},
    }
    current = _snapshot(descriptor)
    current["triggers"].append({
        "trigger_name": "other_owner_before_update", **guard, "event_manipulation": "UPDATE",
    })
    state = lambda value: migration.local_additive_descriptor_state(
        value, descriptor, "synthetic-parent-metadata"
    )
    assert state(current) == "exact"
    missing = deepcopy(current)
    missing["triggers"] = [row for row in missing["triggers"] if row["trigger_name"] != "declared_parent_delete"]
    assert state(missing) == "partial"
    drift = deepcopy(current)
    drift["triggers"][0]["action_statement"] = "BEGIN SET @unexpected=1; END"
    assert state(drift) == "drift"
    complete_owner = deepcopy(descriptor)
    complete_owner["tables"] = complete_owner["parent_columns"]
    complete_owner["parent_columns"] = {}
    assert migration.local_additive_descriptor_state(
        current, complete_owner, "synthetic-complete-table-metadata"
    ) == "drift"


def test_1060_original_registry_oracle_accepts_other_existing_guard():
    """1060 uses its original dedicated oracle before generic metadata comparison."""
    artifact = "1060_registry_case_deletion_guards.sql"
    guards = migration._registry_guard_metadata()["successor_triggers"]
    original = migration._canonical_artifact_descriptor("111_client_finance_ledger.sql")
    name = "trg_client_ledger_entries_before_update"
    assert name not in guards
    guard = original["triggers"][name]
    assert any(value["event_object_table"] == guard["event_object_table"] for value in guards.values())
    metadata = {"triggers": [{"trigger_name": key, **value} for key, value in guards.items()]}
    metadata["triggers"].append({"trigger_name": name, **guard})
    assert migration._registry_guard_snapshot(metadata, artifact)[1] == "exact"
    assert migration._metadata_state_for_artifact(
        metadata, migration._canonical_artifact_descriptor(artifact), artifact,
        defer_missing_triggers=False,
    ) == "exact"
