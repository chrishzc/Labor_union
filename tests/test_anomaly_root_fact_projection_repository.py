from datetime import datetime

from infrastructure.mysql.anomaly_root_fact_projection_repository import _root_snapshot


def test_recovery_query_rehydrates_immutable_owner_bindings_from_current_projection() -> None:
    snapshot = _root_snapshot(_row())

    assert snapshot["recovery_bindings"] == {
        "overpayment_identity": "government-overpayment:bank-7",
        "overpayment_version": 3,
    }


def test_recovery_query_omits_malformed_current_recovery_bindings() -> None:
    row = _row()
    row["current_display_snapshot"] = {"recovery_bindings": ["not-an-object"]}

    assert "recovery_bindings" not in _root_snapshot(row)


def _row() -> dict[str, object]:
    return {
        "finance_import_row_id": 7,
        "finance_import_batch_id": 3,
        "source_occurred_at": datetime(2026, 8, 11),
        "amount_delta_ntd": 0,
        "affected_order_identities": "[]",
        "affected_obligation_identities": "[]",
        "domain_blockers": "[]",
        "reason_codes": "[\"government_subsidy_overpayment_established\"]",
        "root_condition_active": 1,
        "integrity_blocker_active": 0,
        "snapshot_source_version": 9,
        "current_display_snapshot": {
            "recovery_bindings": {
                "overpayment_identity": "government-overpayment:bank-7",
                "overpayment_version": 3,
            }
        },
    }
