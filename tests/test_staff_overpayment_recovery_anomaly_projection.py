"""
File: test_staff_overpayment_recovery_anomaly_projection.py
Description: 驗證 Staff recovery 根事實依 matching 狀態提供 exact owner actions 與解除投影。
"""

from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import build_finance_manual_review_candidate
from subsystems.anomalies.staff_overpayment_recovery_anomaly_consumer import (
    build_staff_overpayment_recovery_root_fact,
)


def test_staff_matching_projects_complete_dispatcher_bindings() -> None:
    fact = build_staff_overpayment_recovery_root_fact(
        {"id": 8, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {
            "matching_identity": "staff-recovery-match:1", "recovery_identity": "recovery-1",
            "staff_id": 7, "finance_import_row_id": 11, "recovery_version": 4,
            "staff_payables_version": 9, "matching_version": 1, "batch_id": 2,
            "finance_import_batch_id": 2, "remaining_amount_ntd": 1000,
            "status": "open",
        },
    )
    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), fact)
    action = candidate.available_actions[0]
    assert action.action_key == "collect_staff_overpayment_recovery"
    assert action.source_bindings["matching_identity"] == "staff-recovery-match:1"


def test_staff_open_recovery_offers_matching_and_exact_adjustment_contracts() -> None:
    fact = build_staff_overpayment_recovery_root_fact(
        {"id": 7, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {
            "recovery_identity": "recovery-1", "staff_id": 7,
            "finance_import_row_id": 11, "recovery_version": 3,
            "staff_payables_version": 8, "batch_id": 2,
            "finance_import_batch_id": 2, "remaining_amount_ntd": 1000,
            "status": "open",
        },
    )

    actions = build_finance_manual_review_candidate(
        default_anomaly_registry(), fact
    ).available_actions

    assert [item.action_key for item in actions] == [
        "match_staff_overpayment_recovery",
        "adjust_staff_overpayment_recovery",
    ]
    assert all(item.source_binding_keys == (
        "recovery_identity", "recovery_version", "staff_id", "staff_payables_version"
    ) for item in actions)
    assert all("finance_import_row_identity" not in item.source_bindings for item in actions)


def test_staff_collected_event_can_close_recovery_projection() -> None:
    fact = build_staff_overpayment_recovery_root_fact(
        {"id": 9, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {"matching_identity": "staff-recovery-match:1", "recovery_identity": "recovery-1", "staff_id": 7, "finance_import_row_id": 11, "recovery_version": 5, "staff_payables_version": 10, "matching_version": 1, "batch_id": 2, "finance_import_batch_id": 2, "remaining_amount_ntd": 0, "status": "recovered"},
    )
    assert fact.active is False
