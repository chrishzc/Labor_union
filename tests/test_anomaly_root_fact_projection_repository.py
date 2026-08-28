"""
File: test_anomaly_root_fact_projection_repository.py
Description: 驗證 root-fact projection 保存 owner domain 並重建不可變 owner bindings。
"""

from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry, reduce_current_alert
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
    build_finance_manual_review_candidate,
)
from infrastructure.mysql.anomaly_root_fact_projection_repository import (
    _insert_current,
    _root_snapshot,
)


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


def test_insert_current_persists_registry_owner_domain() -> None:
    candidate = build_finance_manual_review_candidate(
        default_anomaly_registry(),
        FinanceManualReviewRootFact(
            source_event_identity="government-overpayment:over-1:1",
            source_version=1,
            origin=RootFactEventOrigin.DOMAIN_EVENT,
            occurred_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            finance_import_row_id=7,
            finance_import_batch_id=3,
            active=True,
            integrity_blocker_active=False,
            amount_delta_ntd=500,
            definition_code="GOVSUB-006",
            source_identity_override="government-overpayment:over-1",
            recovery_bindings=(
                ("overpayment_identity", "over-1"),
                ("overpayment_version", 1),
            ),
        ),
    )
    cursor = _RecordingCursor()

    resulting = reduce_current_alert(default_anomaly_registry(), candidate.desired, None)
    assert resulting is not None
    _insert_current(cursor, resulting, candidate)

    assert cursor.parameters[2] == "government_subsidy"


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


class _RecordingCursor:
    def execute(self, _sql, parameters) -> None:
        self.parameters = parameters
