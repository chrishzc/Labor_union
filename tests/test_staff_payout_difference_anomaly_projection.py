from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import build_finance_manual_review_candidate
from subsystems.anomalies.staff_payout_difference_anomaly_consumer import (
    build_staff_payout_difference_root_fact,
)


def test_underpayment_source_projects_a_state_only_alert() -> None:
    root_fact = build_staff_payout_difference_root_fact(_event(), _source("underpayment", True))

    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), root_fact)

    assert candidate.desired.definition_code == "staff_payout_underpayment"
    assert candidate.available_actions == ()
    assert candidate.desired.active is True


def test_recovered_overpayment_source_projects_an_inactive_alert() -> None:
    root_fact = build_staff_payout_difference_root_fact(_event(), _source("overpayment", False))

    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), root_fact)

    assert candidate.desired.definition_code == "staff_payout_overpayment"
    assert candidate.desired.active is False


def _event() -> dict[str, object]:
    return {"id": 8, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)}


def _source(mode: str, active: bool) -> dict[str, object]:
    return {
        "payout_difference_identity": "difference-1", "staff_id": 7,
        "difference_mode": mode, "resulting_staff_payables_version": 3,
        "finance_import_row_id": 11, "batch_id": 5, "active": active,
    }
