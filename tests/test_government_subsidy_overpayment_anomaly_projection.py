from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
    build_finance_manual_review_candidate,
)
from subsystems.anomalies.root_fact_projection_workflow import _bound_registry_actions


def test_government_overpayment_root_fact_exposes_bound_typed_action() -> None:
    root_fact = FinanceManualReviewRootFact(
        source_event_identity="government-overpayment:over-1:1",
        source_version=1,
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        finance_import_row_id=7,
        finance_import_batch_id=3,
        active=True,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        definition_code="GOVSUB-006",
        source_identity_override="government-overpayment:over-1",
        recovery_bindings=(("overpayment_identity", "over-1"), ("overpayment_version", 1)),
    )
    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), root_fact)
    action = candidate.available_actions[0]
    assert action.action_key == "dispose_government_subsidy_overpayment"
    assert action.source_bindings == {"overpayment_identity": "over-1", "overpayment_version": 1}


def test_stored_government_root_snapshot_rehydrates_the_bound_registry_action() -> None:
    descriptor = default_anomaly_registry().require("GOVSUB-006").available_actions[0]

    actions = _bound_registry_actions(
        (descriptor,),
        {
            "source_version": 1,
            "recovery_bindings": {
                "overpayment_identity": "over-1",
                "overpayment_version": 1,
            },
        },
    )

    assert len(actions) == 1
    assert actions[0].action_key == "dispose_government_subsidy_overpayment"
    assert actions[0].source_bindings == {
        "overpayment_identity": "over-1",
        "overpayment_version": 1,
    }
