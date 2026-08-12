from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import build_finance_manual_review_candidate
from subsystems.anomalies.client_refund_underpayment_anomaly_consumer import (
    build_client_refund_underpayment_root_fact,
    consume_client_refund_underpayment_anomaly_events,
)
import pytest


def test_open_refund_underpayment_projects_state_only_alert() -> None:
    root_fact = build_client_refund_underpayment_root_fact(_event(), _source(True))
    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), root_fact)
    assert candidate.desired.definition_code == "client_refund_underpayment"
    assert candidate.desired.active is True
    assert candidate.available_actions == ()


def test_settled_refund_underpayment_projects_inactive_alert() -> None:
    root_fact = build_client_refund_underpayment_root_fact(_event(), _source(False))
    candidate = build_finance_manual_review_candidate(default_anomaly_registry(), root_fact)
    assert candidate.desired.active is False


def test_underpayment_consumer_rejects_an_invalid_page_size() -> None:
    with pytest.raises(ValueError, match="maximum events"):
        consume_client_refund_underpayment_anomaly_events(object(), maximum_events=0)


def _event():
    return {"id": 7, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc)}


def _source(active):
    return {"underpayment_identity": "under-1", "case_no": "C-1", "resulting_account_version": 3, "finance_import_row_id": 11, "batch_id": 4, "active": active}
