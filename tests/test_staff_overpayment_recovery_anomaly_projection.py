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
        },
    )
    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), fact)
    action = candidate.available_actions[0]
    assert action.action_key == "collect_staff_overpayment_recovery"
    assert action.source_bindings["matching_identity"] == "staff-recovery-match:1"


def test_staff_collected_event_can_close_recovery_projection() -> None:
    fact = build_staff_overpayment_recovery_root_fact(
        {"id": 9, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {"matching_identity": "staff-recovery-match:1", "recovery_identity": "recovery-1", "staff_id": 7, "finance_import_row_id": 11, "recovery_version": 5, "staff_payables_version": 10, "matching_version": 1, "batch_id": 2},
        active=False,
    )
    assert fact.active is False
