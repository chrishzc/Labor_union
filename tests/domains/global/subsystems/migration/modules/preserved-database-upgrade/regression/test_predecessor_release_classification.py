from __future__ import annotations

import pytest

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


def test_refund_overage_receipt_accepts_only_exact_predecessor_or_appended_successor():
    artifact = "1058_client_refund_overage_receipt.sql"
    descriptor = migration._canonical_artifact_descriptor(artifact)
    assert descriptor["parent_columns"]["client_refund_reversal_apply_receipts"]["correction_type"]["column_type"] == "enum('refund','refund_return','reversal','refund_overage')"
    snapshot = _empty_snapshot()
    snapshot["columns"].append({
        "table_name": "client_refund_reversal_apply_receipts", "column_name": "correction_type",
        "column_type": "enum('refund','refund_return','reversal')", "is_nullable": "NO",
        "column_default": None, "extra": "",
    })
    assert migration.local_additive_descriptor_state(snapshot, descriptor, artifact) == "absent"
    snapshot["columns"][0]["column_type"] = "enum('refund','refund_return','reversal','refund_overage')"
    assert migration.local_additive_descriptor_state(snapshot, descriptor, artifact) == "exact"
    snapshot["columns"][0]["column_type"] = "enum('refund','reversal','refund_return','refund_overage')"
    assert migration.local_additive_descriptor_state(snapshot, descriptor, artifact) == "drift"


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


def test_104_accepts_exact_historical_accounting_check_successor() -> None:
    predecessor = "104_order_lifecycle_state_history.sql"
    historical_descriptor = migration._canonical_artifact_descriptor(
        HISTORICAL_ACCOUNTING_ARTIFACT
    )
    allowed_successors = migration._allowed_later_artifact_checks(predecessor)
    check_keys = (
        (
            "order_lifecycle_state_events",
            "chk_order_lifecycle_state_event_before_status",
        ),
        (
            "order_lifecycle_state_events",
            "chk_order_lifecycle_state_event_after_status",
        ),
    )

    assert {
        key: allowed_successors[key][-1]
        for key in check_keys
    } == {
        key: historical_descriptor["checks"][key]
        for key in check_keys
    }


def test_refund_overage_local_runner_accepts_only_the_ordinal_preserving_append():
    statement = migration.split_sql((migration.ROOT / "db/schema_parts/1058_client_refund_overage_receipt.sql").read_text(encoding="utf-8"))[0]
    assert migration._local_classify_statement(statement) == "client_refund_overage_receipt_enum_widen"
    for wrong in (
        statement.replace("'refund_return', 'reversal'", "'reversal', 'refund_return'"),
        statement.replace("'refund_return', ", ""),
        statement.replace("'refund_overage'", "'unsupported'"),
        statement.replace("client_refund_reversal_apply_receipts", "other_receipts"),
    ):
        with pytest.raises(migration.LocalAdditiveBlocked) as caught:
            migration._local_classify_statement(wrong)
        assert caught.value.code == "forbidden_sql_effect"
