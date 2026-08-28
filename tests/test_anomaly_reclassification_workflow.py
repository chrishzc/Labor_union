"""
File: test_anomaly_reclassification_workflow.py
Description: 驗證異常必要性移轉 workflow 的 Q/P/A、冪等與有界游標語意。
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationCursor,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationDisposition,
    AnomalyReclassificationPage,
    AnomalyReclassificationReceipt,
    AnomalyReclassificationTargetBinding,
    preview_anomaly_reclassification,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.anomalies.maintenance_workflow import (
    AnomalyMaintenanceApplication,
)


_ACTOR = ActorContext("migration-runner")
_TARGET = AnomalyReclassificationTargetBinding("orders", "work-item:1", 4)
_ELIGIBLE = (
    "DOC-SEND-001",
    "LINE-002",
    "ORDER-001",
    "ORDER-002",
    "ORDER-003",
    "ORDER-004",
    "SCHEDULE-005",
    "SUBSIDYADVANCE-001",
    "staff_payout_overpayment",
)


def _alert(
    source: str, value: str, definition: str = "ORDER-001"
) -> AnomalyReclassificationAlertIdentity:
    return AnomalyReclassificationAlertIdentity(
        PreviewFingerprint(value * 64), definition, source, 7, 3
    )


class _Uow:
    entered = 0
    committed = 0

    def __enter__(self):
        type(self).entered += 1
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        type(self).committed += 1

    def rollback(self):
        return None

    def savepoint(self):
        return object()

    def rollback_to_savepoint(self, token):
        del token

    def release_savepoint(self, token):
        del token


class _TargetVerifier:
    def __init__(self, targets):
        self.targets = targets

    def load_reclassification_target(self, target, *, for_update):
        del for_update
        return self.targets.get(target.target_reference)


class _FirstTargetMissingVerifier(_TargetVerifier):
    def __init__(self, targets):
        super().__init__(targets)
        self.calls = 0

    def load_reclassification_target(self, target, *, for_update):
        self.calls += 1
        if self.calls == 1:
            return None
        return super().load_reclassification_target(target, for_update=for_update)


class _Registry:
    def reclassification_codes(self):
        return (
            "DOC-SEND-001",
            "LINE-002",
            "ORDER-001",
            "ORDER-002",
            "ORDER-003",
            "ORDER-004",
            "SCHEDULE-005",
            "SUBSIDYADVANCE-001",
            "staff_payout_overpayment",
        )


class _Port:
    def __init__(self, alerts, *, page=None):
        self.alerts = {item.source_identity: item for item in alerts}
        self.page = page
        self.receipts = {}
        self.persisted = []
        self.batch_receipts = []
        self.batch_receipts_by_key = {}
        self.query_calls = 0

    def query_reclassification_page(
        self, request, *, eligible_definitions=None
    ):
        del request
        self.query_calls += 1
        if any(
            item.definition_code not in eligible_definitions
            for item in self.alerts.values()
        ):
            raise ValueError("ineligible")
        if self.query_calls > 1 and self.page is not None:
            return AnomalyReclassificationPage((), None)
        return self.page or AnomalyReclassificationPage(
            tuple(sorted(self.alerts.values(), key=lambda item: (item.definition_code, item.source_identity))),
            None,
        )

    def load_reclassification_alert(self, alert, *, for_update):
        del for_update
        return self.alerts.get(alert.source_identity)

    def find_reclassification_batch_receipt(self, key, *, for_update=False):
        del for_update
        return self.batch_receipts_by_key.get(key.value)

    def find_reclassification_receipt(self, key, *, for_update=False):
        del for_update
        return self.receipts.get(key.value)

    def persist_reclassification(
        self, request, candidate=None, receipt=None, command_fingerprint=None
    ):
        del receipt, command_fingerprint
        self.persisted.append(request)
        receipt = AnomalyReclassificationReceipt(
            request.disposition_identity,
            f"receipt:{request.idempotency_key.value}",
            request.disposition,
            request.alert,
            request.preview_fingerprint,
            request.idempotency_key,
            request.correlation_id,
            request.actor,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            len(self.persisted),
            request.alert.workflow_version + 1,
            request.alert.alert_fingerprint,
            PreviewFingerprint("f" * 64),
        )
        self.receipts[request.idempotency_key.value] = (
            candidate.fingerprint,
            receipt,
        )
        self.alerts.pop(request.alert.source_identity)
        return receipt

    def save_reclassification_batch_receipt(
        self,
        request=None,
        result=None,
        before_fingerprints=(),
        after_fingerprints=(),
        *,
        operation_identity=None,
        request_fingerprint=None,
        actor=None,
        correlation_id=None,
    ):
        del operation_identity, request_fingerprint, actor, correlation_id
        self.batch_receipts.append(
            (request, result, before_fingerprints, after_fingerprints)
        )
        batch_identity = f"batch:{len(self.batch_receipts)}"
        self.batch_receipts_by_key[request.idempotency_key.value] = (
            request.request_fingerprint,
            replace(result, batch_receipt_identity=batch_identity),
        )
        return batch_identity


def _candidate(alert, reason="reviewed"):
    return preview_anomaly_reclassification(
        disposition=AnomalyReclassificationDisposition.RECLASSIFIED_TO_OWNER_WORK_ITEM,
        alert=alert,
        target=_TARGET,
        actor=_ACTOR,
        reason=reason,
        evidence_reference="evidence:work-item",
    )


def _app(port, *, target_verifier=None):
    return AnomalyMaintenanceApplication(
        registry=_Registry(),
        scan_port=object(),
        retry_port=object(),
        projector=object(),
        unit_of_work_factory=_Uow,
        reclassification_port=port,
        target_verifier=target_verifier
        or _TargetVerifier({_TARGET.target_reference: _TARGET}),
    )


def test_preview_is_zero_write_and_apply_fresh_locks_once():
    _Uow.entered = _Uow.committed = 0
    alert = _alert("order:1", "a")
    port = _Port((alert,))
    app = _app(port)
    preview = app.preview_reclassification(
        alert,
        AnomalyReclassificationDisposition.RECLASSIFIED_TO_OWNER_WORK_ITEM,
        _TARGET,
        _ACTOR,
        "reviewed",
        "evidence:work-item",
    )
    assert preview.alert == alert
    assert _Uow.entered == 0
    request = AnomalyReclassificationApplyRequest.from_preview(
        preview,
        idempotency_key=IdempotencyKey("apply:order:1"),
        correlation_id=CorrelationId("corr:order:1"),
    )
    receipt = app.apply_reclassification(request)
    assert receipt.resulting_predicate_active is False
    assert _Uow.entered == _Uow.committed == 1
    assert len(port.persisted) == 1

def test_apply_replays_and_rejects_same_key_with_different_preview():
    alert = _alert("order:1", "a")
    port = _Port((alert,))
    app = _app(port)
    first_preview = _candidate(alert)
    first = app.apply_reclassification(
        AnomalyReclassificationApplyRequest.from_preview(
            first_preview,
            idempotency_key=IdempotencyKey("apply:order:1"),
            correlation_id=CorrelationId("corr:order:1"),
        )
    )
    replay = app.apply_reclassification(
        AnomalyReclassificationApplyRequest.from_preview(
            first_preview,
            idempotency_key=IdempotencyKey("apply:order:1"),
            correlation_id=CorrelationId("corr:order:1"),
        )
    )
    assert replay.replayed is True
    assert replay.receipt_identity == first.receipt_identity
    changed = _candidate(alert, "changed")
    changed_request = AnomalyReclassificationApplyRequest.from_preview(
        changed,
        idempotency_key=IdempotencyKey("apply:order:1"),
        correlation_id=CorrelationId("corr:order:1"),
    )
    with pytest.raises(ValueError, match="idempotency_conflict"):
        app.apply_reclassification(changed_request)
    assert len(port.persisted) == 1


def test_apply_rejects_target_version_drift_before_any_persistence() -> None:
    alert = _alert("order:1", "a")
    port = _Port((alert,))
    verifier = _TargetVerifier({_TARGET.target_reference: _TARGET})
    app = _app(port, target_verifier=verifier)
    preview = app.preview_reclassification(
        alert,
        AnomalyReclassificationDisposition.RECLASSIFIED_TO_OWNER_WORK_ITEM,
        _TARGET,
        _ACTOR,
        "reviewed",
        "evidence:work-item",
    )
    verifier.targets[_TARGET.target_reference] = AnomalyReclassificationTargetBinding(
        _TARGET.target_domain,
        _TARGET.target_reference,
        _TARGET.target_version + 1,
    )

    with pytest.raises(ValueError, match="anomaly_reclassification_stale_target"):
        app.apply_reclassification(
            AnomalyReclassificationApplyRequest.from_preview(
                preview,
                idempotency_key=IdempotencyKey("apply:order:1"),
                correlation_id=CorrelationId("corr:order:1"),
            )
        )

    assert port.persisted == []


def test_runner_accepts_partial_page_and_records_blocker_without_marking_complete():
    _Uow.entered = _Uow.committed = 0
    first = _alert("order:1", "a")
    second = _alert("order:2", "b")
    page = AnomalyReclassificationPage(
        (first, second), AnomalyReclassificationCursor("ORDER-001", "order:2")
    )
    port = _Port((first, second), page=page)
    result = _app(port).run_reclassification_batch(
        AnomalyReclassificationCursorPageRequest(maximum_items=2),
        eligible_codes=_ELIGIBLE,
        operation_identity="migration:orders",
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=lambda alert: (
            _candidate(alert)
            if alert is first
            else (_ for _ in ()).throw(ValueError("target_not_found"))
        ),
        actor=_ACTOR,
    )
    assert result.scanned_count == 2
    assert result.applied_count == 1
    assert result.blocked_count == 1
    assert result.completed is False
    assert result.batch_receipt_identity == "batch:1"
    assert _Uow.entered == _Uow.committed == 1
    assert len(port.batch_receipts) == 1


def test_runner_sorts_mixed_resolver_and_apply_blockers_by_full_item_key():
    first = _alert("order:1", "a", "ORDER-001")
    second = _alert("order:2", "b", "ORDER-002")
    page = AnomalyReclassificationPage((first, second), None)
    port = _Port((first, second), page=page)
    result = _app(
        port,
        target_verifier=_FirstTargetMissingVerifier(
            {_TARGET.target_reference: _TARGET}
        ),
    ).run_reclassification_batch(
        AnomalyReclassificationCursorPageRequest(maximum_items=2),
        eligible_codes=_ELIGIBLE,
        operation_identity="migration:orders",
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=lambda alert: (
            _candidate(alert)
            if alert is first
            else (_ for _ in ()).throw(ValueError("resolver_blocked"))
        ),
        actor=_ACTOR,
    )
    assert result.applied_count == 0
    assert tuple(
        (item.definition_code, item.source_identity)
        for item in result.blocked_items
    ) == (("ORDER-001", "order:1"), ("ORDER-002", "order:2"))


def test_query_rejects_repeated_cursor_page():
    alert = _alert("order:1", "a")
    page = AnomalyReclassificationPage(
        (alert,), AnomalyReclassificationCursor("ORDER-001", "order:1")
    )
    app = _app(_Port((alert,), page=page))
    with pytest.raises(ValueError, match="not_advanced"):
        app.query_reclassification(
            AnomalyReclassificationCursorPageRequest(
                after=AnomalyReclassificationCursor("ORDER-001", "order:1")
            ),
            eligible_codes=_Registry().reclassification_codes(),
        )


def test_runner_replays_same_operation_and_cursor_and_conflicts_on_changed_candidate():
    _Uow.entered = _Uow.committed = 0
    alert = _alert("order:1", "a")
    page = AnomalyReclassificationPage((alert,), None)
    port = _Port((alert,), page=page)
    app = _app(port)
    request = AnomalyReclassificationCursorPageRequest(maximum_items=1)
    first = app.run_reclassification_batch(
        request,
        eligible_codes=_ELIGIBLE,
        operation_identity="migration:orders",
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=_candidate,
        actor=_ACTOR,
    )
    replay = app.run_reclassification_batch(
        request,
        eligible_codes=_ELIGIBLE,
        operation_identity="migration:orders",
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=_candidate,
        actor=_ACTOR,
    )
    assert replay == first
    assert len(port.persisted) == 1
    assert port.query_calls == 1
    assert _Uow.entered == _Uow.committed == 2

    changed = lambda item: _candidate(item, "changed")
    with pytest.raises(ValueError, match="batch_conflict"):
        app.run_reclassification_batch(
            request,
            eligible_codes=_ELIGIBLE,
            operation_identity="migration:orders",
            policy_identity="policy:v1",
            policy_fingerprint=PreviewFingerprint("2" * 64),
            resolve_candidate=changed,
            actor=_ACTOR,
        )
    assert len(port.persisted) == 1

    with pytest.raises(ValueError, match="batch_conflict"):
        app.run_reclassification_batch(
            request,
            eligible_codes=_ELIGIBLE,
            operation_identity="migration:orders",
            policy_identity="policy:v1",
            policy_fingerprint=PreviewFingerprint("1" * 64),
            resolve_candidate=_candidate,
            actor=ActorContext("other-runner"),
        )

    with pytest.raises(ValueError, match="batch_conflict"):
        app.run_reclassification_batch(
            AnomalyReclassificationCursorPageRequest(maximum_items=2),
            eligible_codes=_ELIGIBLE,
            operation_identity="migration:orders",
            policy_identity="policy:v1",
            policy_fingerprint=PreviewFingerprint("1" * 64),
            resolve_candidate=_candidate,
            actor=_ACTOR,
        )


def test_runner_fails_closed_without_savepoint_and_on_actor_mismatch():
    alert = _alert("order:1", "a")
    page = AnomalyReclassificationPage((alert,), None)
    actor_result = _app(_Port((alert,), page=page)).run_reclassification_batch(
        AnomalyReclassificationCursorPageRequest(),
        eligible_codes=_ELIGIBLE,
        operation_identity="migration:orders",
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=_candidate,
        actor=ActorContext("other-runner"),
    )
    assert actor_result.applied_count == 0
    assert actor_result.blocked_count == 1

    class NoSavepointUow:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            raise AssertionError("must not commit")

        def rollback(self):
            return None

    app = AnomalyMaintenanceApplication(
        _Registry(),
        object(),
        object(),
        object(),
        NoSavepointUow,
        reclassification_port=_Port((alert,), page=AnomalyReclassificationPage((alert,), None)),
        target_verifier=_TargetVerifier({_TARGET.target_reference: _TARGET}),
    )
    with pytest.raises(ValueError, match="savepoint_unavailable"):
        app.run_reclassification_batch(
            AnomalyReclassificationCursorPageRequest(),
            eligible_codes=_ELIGIBLE,
            operation_identity="migration:orders",
            policy_identity="policy:v1",
            policy_fingerprint=PreviewFingerprint("1" * 64),
            resolve_candidate=_candidate,
            actor=_ACTOR,
        )


def test_runner_rejects_code_outside_registry_and_hashes_long_operation_identity():
    alert = _alert("order:1", "a")
    page = AnomalyReclassificationPage((alert,), None)
    port = _Port((alert,), page=page)
    app = _app(port)
    with pytest.raises(ValueError, match="not_allowed"):
        app.run_reclassification_batch(
            AnomalyReclassificationCursorPageRequest(),
            eligible_codes=("ORDER-001", "ORDER-999"),
            operation_identity="migration:orders",
            policy_identity="policy:v1",
            policy_fingerprint=PreviewFingerprint("1" * 64),
            resolve_candidate=_candidate,
            actor=_ACTOR,
        )
    result = app.run_reclassification_batch(
        AnomalyReclassificationCursorPageRequest(),
        eligible_codes=_ELIGIBLE,
        operation_identity="o" * 180,
        policy_identity="policy:v1",
        policy_fingerprint=PreviewFingerprint("1" * 64),
        resolve_candidate=_candidate,
        actor=_ACTOR,
    )
    assert result.applied_count == 1
    assert len(port.persisted[0].idempotency_key.value) <= 191
