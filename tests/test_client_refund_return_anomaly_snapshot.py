"""
File: test_client_refund_return_anomaly_snapshot.py
Description: 驗證退款退匯 root snapshot 持久化、回讀與 recovery action 門禁。
"""

from datetime import datetime, timezone
import json

import pytest

from api.routes.anomaly_recovery import _root_snapshot_payload
from domains.anomalies.registry import (
    AlertWorkflowStatus,
    CurrentAlertProjection,
    default_anomaly_registry,
)
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
    build_finance_manual_review_candidate,
)
from infrastructure.mysql.anomaly_root_fact_projection_repository import (
    _insert_current,
    _root_snapshot,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.root_fact_projection_workflow import (
    StoredRecoveryProjection,
    _recovery_actions,
)


def test_current_json_round_trip_preserves_original_refund_ledger_entry_id() -> None:
    candidate = build_finance_manual_review_candidate(
        default_anomaly_registry(),
        _root_fact(),
    )
    resulting = CurrentAlertProjection(
        fingerprint=candidate.alert_fingerprint,
        definition_code="CLIENTREFUND-001",
        source_identity="finance-import-refund-return:71:41",
        source_version=12,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=1,
    )
    cursor = _RecordingCursor()

    _insert_current(cursor, resulting, candidate)
    persisted_json = json.loads(cursor.parameters[-1])
    row = _relational_snapshot_row(persisted_json)

    assert persisted_json["original_refund_ledger_entry_id"] == 41
    assert _root_snapshot(row)["original_refund_ledger_entry_id"] == 41


@pytest.mark.parametrize(
    "missing_key",
    ("finance_import_row_id", "original_refund_ledger_entry_id", "affected_obligation_identities"),
)
def test_refund_return_action_fails_closed_when_any_required_root_binding_is_missing(
    missing_key: str,
) -> None:
    row = _relational_snapshot_row(
        {
            "original_refund_ledger_entry_id": 41,
            "recovery_bindings": {},
        }
    )
    snapshot = _root_snapshot(row)
    snapshot.pop(missing_key, None)
    stored = _stored(snapshot)

    assert _recovery_actions(
        default_anomaly_registry().require("CLIENTREFUND-001"), stored
    ) == ()


def test_refund_return_action_binds_actual_row_and_requires_operator_confirmation_inputs() -> None:
    action = _recovery_actions(
        default_anomaly_registry().require("CLIENTREFUND-001"),
        _stored(
            _root_snapshot(
                _relational_snapshot_row(
                    {"original_refund_ledger_entry_id": 41}
                )
            )
        ),
    )[0]

    assert action.source_bindings == {
        "finance_import_row_identity": "finance-import-row:71",
        "source_version": 12,
    }
    assert action.required_operator_inputs == (
        "evidence",
        "reason",
        "refund_ledger_entry_identity",
        "target_obligation_identities",
    )


def test_typed_recovery_snapshot_exposes_ledger_and_obligation_targets() -> None:
    view = _root_snapshot_payload(
        _root_snapshot(
            _relational_snapshot_row({"original_refund_ledger_entry_id": 41})
        )
    )

    assert view.original_refund_ledger_entry_identity == "41"
    assert view.affected_obligation_identities == ["refund:1"]


def _root_fact() -> FinanceManualReviewRootFact:
    return FinanceManualReviewRootFact(
        source_event_identity="client-refund-return-review:12",
        source_version=12,
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        finance_import_row_id=71,
        finance_import_batch_id=4,
        active=True,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        affected_order_identities=("case:1",),
        affected_obligation_identities=("refund:1",),
        domain_blockers=("refund_return_requires_confirmed_reversal",),
        reason_codes=("refund_return_review_recorded",),
        definition_code="CLIENTREFUND-001",
        source_identity_override="finance-import-refund-return:71:41",
        original_refund_ledger_entry_id=41,
    )


def _stored(snapshot: dict[str, object]) -> StoredRecoveryProjection:
    return StoredRecoveryProjection(
        projection=CurrentAlertProjection(
            fingerprint=PreviewFingerprint("a" * 64),
            definition_code="CLIENTREFUND-001",
            source_identity="finance-import-refund-return:71:41",
            source_version=12,
            predicate_active=True,
            workflow_status=AlertWorkflowStatus.OPEN,
            workflow_version=1,
        ),
        root_fact_snapshot=snapshot,
        projection_freshness="current",
        occurrence_timeline=(),
        workflow_timeline=(),
    )


def _relational_snapshot_row(current_display_snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "finance_import_row_id": 71,
        "finance_import_batch_id": 4,
        "source_occurred_at": datetime(2026, 8, 4),
        "amount_delta_ntd": 0,
        "affected_order_identities": '["case:1"]',
        "affected_obligation_identities": '["refund:1"]',
        "domain_blockers": '["refund_return_requires_confirmed_reversal"]',
        "reason_codes": '["refund_return_review_recorded"]',
        "root_condition_active": 1,
        "integrity_blocker_active": 0,
        "snapshot_source_version": 12,
        "current_display_snapshot": current_display_snapshot,
    }


class _RecordingCursor:
    def execute(self, _sql, parameters) -> None:
        self.parameters = parameters
