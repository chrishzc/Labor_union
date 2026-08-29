"""
File: test_anomaly_reclassification_domain.py
Description: 驗證異常必要性移轉的純 Domain immutable contract。
"""

from datetime import datetime, timezone

import pytest

from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationBlockedItem,
    AnomalyReclassificationCursor,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationDisposition,
    AnomalyReclassificationPage,
    AnomalyReclassificationReceipt,
    AnomalyReclassificationResult,
    AnomalyReclassificationTargetBinding,
    preview_anomaly_reclassification,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


_ALERT = AnomalyReclassificationAlertIdentity(
    PreviewFingerprint("a" * 64), "SCHEDULE-005", "schedule:42", 7, 3
)
_ACTOR = ActorContext("migration-runner")
_TARGET = AnomalyReclassificationTargetBinding("orders", "work-item:42", 4)


def _preview(disposition=AnomalyReclassificationDisposition.RECLASSIFIED_TO_OWNER_WORK_ITEM):
    retired = disposition is AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE
    return preview_anomaly_reclassification(
        disposition=disposition,
        alert=_ALERT,
        target=None if retired else _TARGET,
        actor=_ACTOR,
        reason="necessity migration evidence reviewed",
        evidence_reference="evidence:anomaly:42",
        rulebook_reference="spec:06:necessity" if retired else None,
        release_evidence_reference="receipt:rulebook:v1" if retired else None,
    )


def test_disposition_enum_is_exactly_three_values() -> None:
    assert tuple(item.value for item in AnomalyReclassificationDisposition) == (
        "reclassified_to_owner_work_item",
        "retired_false_positive",
        "replaced_by_successor",
    )


def test_target_binding_is_all_or_none_and_required_for_targeted_dispositions() -> None:
    assert AnomalyReclassificationTargetBinding() == AnomalyReclassificationTargetBinding(
        None, None, None
    )
    with pytest.raises(ValueError, match="incomplete"):
        AnomalyReclassificationTargetBinding("orders", "work-item:42", None)
    with pytest.raises(ValueError, match="target is required"):
        preview_anomaly_reclassification(
            disposition=AnomalyReclassificationDisposition.REPLACED_BY_SUCCESSOR,
            alert=_ALERT,
            target=None,
            actor=_ACTOR,
            reason="successor was checked",
            evidence_reference="evidence:42",
        )
    with pytest.raises(ValueError, match="cannot have a target"):
        preview_anomaly_reclassification(
            disposition=AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE,
            alert=_ALERT,
            target=_TARGET,
            actor=_ACTOR,
            reason="rulebook says this is not an anomaly",
            evidence_reference="evidence:42",
            rulebook_reference="spec:06:necessity",
            release_evidence_reference="receipt:rulebook:v1",
        )


def test_retired_disposition_requires_both_retirement_evidence_references() -> None:
    with pytest.raises(ValueError, match="requires rulebook"):
        preview_anomaly_reclassification(
            disposition=AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE,
            alert=_ALERT,
            target=None,
            actor=_ACTOR,
            reason="rulebook says this is not an anomaly",
            evidence_reference="evidence:42",
        )
    with pytest.raises(ValueError, match="supplied together"):
        preview_anomaly_reclassification(
            disposition=AnomalyReclassificationDisposition.REPLACED_BY_SUCCESSOR,
            alert=_ALERT,
            target=_TARGET,
            actor=_ACTOR,
            reason="successor was checked",
            evidence_reference="evidence:42",
            rulebook_reference="spec:06:necessity",
        )
    optional_pair = preview_anomaly_reclassification(
        disposition=AnomalyReclassificationDisposition.REPLACED_BY_SUCCESSOR,
        alert=_ALERT,
        target=_TARGET,
        actor=_ACTOR,
        reason="successor was checked",
        evidence_reference="evidence:42",
        rulebook_reference="spec:06:necessity",
        release_evidence_reference="receipt:rulebook:v1",
    )
    assert optional_pair.rulebook_reference == "spec:06:necessity"


def test_preview_fingerprint_is_stable_and_sensitive_to_contract_inputs() -> None:
    baseline = _preview()
    assert baseline.fingerprint == _preview().fingerprint
    changed_reason = preview_anomaly_reclassification(
        disposition=baseline.disposition,
        alert=baseline.alert,
        target=baseline.target,
        actor=baseline.actor,
        reason="different reviewed reason",
        evidence_reference=baseline.evidence_reference,
    )
    changed_target = preview_anomaly_reclassification(
        disposition=baseline.disposition,
        alert=baseline.alert,
        target=AnomalyReclassificationTargetBinding("orders", "work-item:99", 4),
        actor=baseline.actor,
        reason=baseline.reason,
        evidence_reference=baseline.evidence_reference,
    )
    changed_actor = preview_anomaly_reclassification(
        disposition=baseline.disposition,
        alert=baseline.alert,
        target=baseline.target,
        actor=ActorContext("different-runner", ("migration",)),
        reason=baseline.reason,
        evidence_reference=baseline.evidence_reference,
    )
    assert baseline.fingerprint != changed_reason.fingerprint
    assert baseline.fingerprint != changed_target.fingerprint
    assert baseline.fingerprint != changed_actor.fingerprint


def test_cursor_page_requires_lexicographic_order_and_bound() -> None:
    first = AnomalyReclassificationAlertIdentity(
        PreviewFingerprint("b" * 64), "ORDER-001", "order:2", 1, 0
    )
    second = AnomalyReclassificationAlertIdentity(
        PreviewFingerprint("c" * 64), "ORDER-001", "order:3", 1, 0
    )
    page = AnomalyReclassificationPage(
        (first, second), AnomalyReclassificationCursor("ORDER-001", "order:3")
    )
    assert page.next_cursor.key == ("ORDER-001", "order:3")
    with pytest.raises(ValueError, match="must equal last"):
        AnomalyReclassificationPage(
            (first, second), AnomalyReclassificationCursor("ORDER-001", "order:4")
        )
    with pytest.raises(ValueError, match="strictly ordered"):
        AnomalyReclassificationPage((second, first), None)
    with pytest.raises(ValueError, match="exceeds maximum"):
        AnomalyReclassificationPage(tuple(first for _ in range(101)), None)
    with pytest.raises(ValueError, match="exceeds maximum"):
        AnomalyReclassificationCursorPageRequest(maximum_items=101)
    with pytest.raises(ValueError, match="bounded operation size"):
        AnomalyReclassificationCursorPageRequest(maximum_items=0)


def test_receipt_and_apply_request_validate_identity_and_replay() -> None:
    preview = _preview()
    request = AnomalyReclassificationApplyRequest.from_preview(
        preview,
        idempotency_key=IdempotencyKey("migration:42"),
        correlation_id=CorrelationId("batch:20260827"),
    )
    assert request.disposition_identity == preview.disposition_identity
    receipt = AnomalyReclassificationReceipt(
        request.disposition_identity,
        "receipt:anomaly:42",
        request.disposition,
        request.alert,
        request.preview_fingerprint,
        request.idempotency_key,
        request.correlation_id,
        request.actor,
        datetime(2026, 8, 27, tzinfo=timezone.utc),
        101,
        request.alert.workflow_version + 1,
        PreviewFingerprint("b" * 64),
        PreviewFingerprint("c" * 64),
        replayed=True,
    )
    assert receipt.replayed is True
    with pytest.raises(ValueError, match="deactivate predicate"):
        AnomalyReclassificationReceipt(
            request.disposition_identity,
            "receipt:anomaly:42",
            request.disposition,
            request.alert,
            request.preview_fingerprint,
            request.idempotency_key,
            request.correlation_id,
            request.actor,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            101,
            request.alert.workflow_version + 1,
            PreviewFingerprint("b" * 64),
            PreviewFingerprint("c" * 64),
            resulting_predicate_active=True,
        )
    with pytest.raises(ValueError, match="workflow version mismatch"):
        AnomalyReclassificationReceipt(
            request.disposition_identity,
            "receipt:anomaly:42",
            request.disposition,
            request.alert,
            request.preview_fingerprint,
            request.idempotency_key,
            request.correlation_id,
            request.actor,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            101,
            request.alert.workflow_version + 2,
            PreviewFingerprint("b" * 64),
            PreviewFingerprint("c" * 64),
        )


def test_result_validates_blockers_and_count_conservation() -> None:
    blocked = AnomalyReclassificationBlockedItem(
        "ORDER-001", "order:2", "owner work item was not found"
    )
    result = AnomalyReclassificationResult(2, 1, (blocked,), None, "batch:42")
    assert result.blocked_count == 1
    assert result.completed is False
    with pytest.raises(ValueError, match="counts are inconsistent"):
        AnomalyReclassificationResult(1, 1, (blocked,), None)
    with pytest.raises(ValueError, match="strictly ordered"):
        AnomalyReclassificationResult(
            2,
            0,
            (blocked, blocked),
            AnomalyReclassificationCursor("ORDER-001", "order:3"),
        )
