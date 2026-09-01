from __future__ import annotations

from scripts import migrate_preserved_database_additive_schema as migration


ARTIFACT = "1005_contract_external_signing_successor.sql"
ORDER_LIFECYCLE_ARTIFACT = "1013_order_lifecycle_pending_status_constraint.sql"
HISTORICAL_ACCOUNTING_ARTIFACT = "1028_historical_service_accounting.sql"


def _empty_snapshot() -> dict[str, list[object] | dict[str, object]]:
    return {
        "columns": [],
        "indexes": [],
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_contract_successor_accepts_exact_pre_1004_dependency_as_absent() -> None:
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    snapshot = _empty_snapshot()

    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ARTIFACT
    ) == "absent"

    snapshot["columns"].append({
        "table_name": "controlled_file_objects",
        "column_name": "purpose",
        "column_type": descriptor["parent_columns"]
        ["controlled_file_objects"]["purpose"]["column_type"],
        "is_nullable": "NO",
        "column_default": None,
        "extra": "",
    })
    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ARTIFACT
    ) == "drift"


def test_1013_accepts_exact_historical_accounting_check_successor() -> None:
    descriptor = migration._canonical_artifact_descriptor(ORDER_LIFECYCLE_ARTIFACT)
    historical_descriptor = migration._canonical_artifact_descriptor(
        HISTORICAL_ACCOUNTING_ARTIFACT
    )
    check_key = (
        "order_lifecycle_state_events",
        "chk_order_lifecycle_state_event_before_status",
    )
    snapshot = _empty_snapshot()
    snapshot["constraints"].append({
        "table_name": check_key[0],
        "constraint_name": check_key[1],
        "constraint_type": "CHECK",
        "check_clause": historical_descriptor["checks"][check_key],
        "enforced": "YES",
    })

    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ORDER_LIFECYCLE_ARTIFACT
    ) == "exact"

    snapshot["constraints"][0]["check_clause"] = (
        "before_status IN ('待補件','未發布狀態')"
    )
    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ORDER_LIFECYCLE_ARTIFACT
    ) == "drift"
