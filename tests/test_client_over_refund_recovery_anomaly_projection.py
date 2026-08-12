from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import build_finance_manual_review_candidate
from subsystems.anomalies.client_over_refund_recovery_anomaly_consumer import (
    build_client_over_refund_recovery_root_fact,
)
from subsystems.anomalies.root_fact_projection_workflow import _bound_registry_actions


def test_client_matching_event_builds_bound_recovery_action() -> None:
    fact = build_client_over_refund_recovery_root_fact(
        {"id": 9, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {
            "matching_identity": "client-recovery-match:1",
            "case_no": "115000001",
            "recovery_identity": "recovery-1",
            "finance_import_row_id": 7,
            "recovery_version": 3,
            "account_version": 4,
            "matching_version": 1,
            "batch_id": 2,
        },
    )

    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), fact)
    action = candidate.available_actions[0]

    assert fact.definition_code == "client_over_refund_recovery_open"
    assert action.action_key == "collect_client_over_refund_recovery"
    assert action.source_bindings["matching_identity"] == "client-recovery-match:1"


def test_stored_client_matching_snapshot_rehydrates_registry_action() -> None:
    descriptor = default_anomaly_registry().require(
        "client_over_refund_recovery_open"
    ).available_actions[0]
    bindings = {
        "account_version": 4,
        "case_no": "115000001",
        "finance_import_row_identity": "7",
        "matching_identity": "client-recovery-match:1",
        "matching_version": 1,
        "recovery_identity": "recovery-1",
        "recovery_version": 3,
    }

    actions = _bound_registry_actions(
        (descriptor,), {"source_version": 9, "recovery_bindings": bindings}
    )

    assert len(actions) == 1
    assert actions[0].source_bindings == bindings


def test_collected_event_can_close_the_same_recovery_projection() -> None:
    fact = build_client_over_refund_recovery_root_fact(
        {"id": 10, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)},
        {
            "matching_identity": "client-recovery-match:1", "case_no": "115000001",
            "recovery_identity": "recovery-1", "finance_import_row_id": 7,
            "recovery_version": 4, "account_version": 5, "matching_version": 1,
            "batch_id": 2,
        },
        active=False,
    )
    assert fact.active is False
