"""
File: test_anomaly_projector_dead_letter_recovery.py
Description: 驗證 projector 死信需具理由、證據、fresh preview 與冪等 receipt 才能人工重試。
"""

from datetime import datetime, timezone

from fastapi import HTTPException
import pytest

from api.routes.anomaly_recovery import (
    _maintenance_contract_error,
    apply_projector_dead_letter_retry,
    apply_projector_dead_letter_supersede,
    preview_projector_dead_letter_retry as preview_retry_route,
    preview_projector_dead_letter_supersede as preview_supersede_route,
)
from api.schemas.anomaly_recovery import (
    RetryProjectorDeadLetterApplyBody,
    RetryProjectorDeadLetterPreviewBody,
    SupersedeProjectorDeadLetterApplyBody,
)
from domains.anomalies.maintenance import (
    ProjectorDeadLetter,
    ProjectorDeadLetterIdentity,
    ProjectorDeadLetterSuccessor,
    RetryProjectorDeadLetterRequest,
    SupersedeProjectorDeadLetterRequest,
    preview_projector_dead_letter_retry,
    preview_projector_dead_letter_supersede,
)
from infrastructure.mysql.anomaly_maintenance_repository import (
    _matching_projection_equivalent,
    _owner_projection_equivalent,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.maintenance_workflow import AnomalyMaintenanceApplication


_NOW = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)


def _dead_letter(attempt_count=3, *, with_successor=False):
    successor = None
    if with_successor:
        successor = ProjectorDeadLetterSuccessor(
            19,
            19,
            PreviewFingerprint("a" * 64),
            False,
        )
    return ProjectorDeadLetter(
        ProjectorDeadLetterIdentity("government_overpayment", 17),
        "government_subsidy_overpayment_offset",
        attempt_count,
        "government_overpayment_projection_failed",
        _NOW,
        successor,
    )


@pytest.mark.parametrize("attempt_count", [1, 2])
def test_dead_letter_rejects_attempt_below_terminal_threshold(attempt_count) -> None:
    with pytest.raises(ValueError, match="below dead-letter threshold"):
        _dead_letter(attempt_count)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


class _RetryPort:
    def __init__(self, dead_letter):
        self.dead_letter = dead_letter
        self.receipts = {}
        self.requeued = []
        self.supersede_receipts = {}

    def load_dead_letter(self, identity, *, for_update):
        del for_update
        if self.dead_letter is None or identity != self.dead_letter.identity:
            return None
        return self.dead_letter

    def load_dead_letter_with_successor(self, identity, *, for_update):
        return self.load_dead_letter(identity, for_update=for_update)

    def load_dead_letter_retry_receipt(self, key, *, for_update):
        del for_update
        return self.receipts.get(key)

    def requeue_dead_letter(self, dead_letter):
        self.requeued.append(dead_letter.identity)

    def save_dead_letter_retry_receipt(self, request, fingerprint, receipt):
        self.receipts[request.idempotency_key.value] = (fingerprint, receipt)

    def load_dead_letter_supersede_receipt(self, key, *, for_update):
        del for_update
        return self.supersede_receipts.get(key)

    def save_dead_letter_supersede_receipt(self, request, fingerprint, receipt):
        self.supersede_receipts[request.idempotency_key.value] = (
            fingerprint,
            receipt,
        )


def _application(retry_port):
    return AnomalyMaintenanceApplication(
        registry=object(),
        scan_port=object(),
        retry_port=retry_port,
        projector=object(),
        unit_of_work_factory=_UnitOfWork,
    )


def _request(dead_letter, *, key="retry-17", fingerprint=None):
    preview = preview_projector_dead_letter_retry(
        dead_letter,
        "已修正來源資料後重新投影",
        "support-call:20260827:17",
    )
    return RetryProjectorDeadLetterRequest(
        dead_letter.identity,
        dead_letter.attempt_count,
        preview.reason,
        preview.evidence_reference,
        fingerprint or preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("system-admin"),
        CorrelationId("retry-projector-17"),
    )


def _supersede_request(dead_letter, *, key="supersede-17", fingerprint=None):
    preview = preview_projector_dead_letter_supersede(
        dead_letter,
        "較高版本已完成投影",
        "incident:20260827:17",
    )
    return SupersedeProjectorDeadLetterRequest(
        dead_letter.identity,
        dead_letter.attempt_count,
        preview.successor.event_id,
        preview.successor.source_version,
        preview.reason,
        preview.evidence_reference,
        fingerprint or preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("system-admin"),
        CorrelationId("supersede-projector-17"),
    )
def test_preview_fingerprint_binds_reason_evidence_and_dead_letter_state() -> None:
    dead_letter = _dead_letter()
    baseline = preview_projector_dead_letter_retry(dead_letter, "來源已修正", "case:17")

    assert baseline.fingerprint != preview_projector_dead_letter_retry(
        dead_letter, "來源已修正", "case:18"
    ).fingerprint
    assert baseline.fingerprint != preview_projector_dead_letter_retry(
        _dead_letter(4), "來源已修正", "case:17"
    ).fingerprint


def test_apply_requeues_once_and_same_idempotency_key_replays_receipt() -> None:
    dead_letter = _dead_letter()
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    request = _request(dead_letter)

    first = application.apply_dead_letter_retry(request)
    replay = application.apply_dead_letter_retry(request)

    assert retry_port.requeued == [dead_letter.identity]
    assert first.resulting_status == "pending"
    assert first.replayed is False
    assert replay.receipt_identity == first.receipt_identity
    assert replay.replayed is True


def test_apply_rejects_stale_attempt_count_without_requeue() -> None:
    dead_letter = _dead_letter(4)
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    stale_request = _request(_dead_letter(3))

    with pytest.raises(ValueError, match="projector_dead_letter_stale"):
        application.apply_dead_letter_retry(stale_request)

    assert retry_port.requeued == []


def test_apply_rejects_reused_idempotency_key_for_different_evidence() -> None:
    dead_letter = _dead_letter()
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    first = _request(dead_letter)
    application.apply_dead_letter_retry(first)
    changed = preview_projector_dead_letter_retry(dead_letter, first.reason, "case:changed")
    conflict = RetryProjectorDeadLetterRequest(
        dead_letter.identity,
        dead_letter.attempt_count,
        changed.reason,
        changed.evidence_reference,
        changed.fingerprint,
        first.idempotency_key,
        first.actor,
        first.correlation_id,
    )

    with pytest.raises(ValueError, match="idempotency_conflict"):
        application.apply_dead_letter_retry(conflict)

    assert retry_port.requeued == [dead_letter.identity]


def test_supersede_requires_verified_successor_and_never_requeues_old_event() -> None:
    without_successor = _dead_letter()
    application = _application(_RetryPort(without_successor))
    with pytest.raises(
        ValueError, match="projector_dead_letter_successor_not_verified"
    ):
        application.preview_dead_letter_supersede(
            without_successor.identity, "reason", "evidence:17"
        )

    dead_letter = _dead_letter(with_successor=True)
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    request = _supersede_request(dead_letter)
    first = application.apply_dead_letter_supersede(request)
    replay = application.apply_dead_letter_supersede(request)

    assert retry_port.requeued == []
    assert first.resulting_status == "superseded_by_verified_successor"
    assert first.successor_event_id == 19
    assert replay.receipt_identity == first.receipt_identity
    assert replay.replayed is True


def test_supersede_rejects_changed_successor_without_receipt() -> None:
    preview_dead_letter = _dead_letter(with_successor=True)
    changed = ProjectorDeadLetter(
        preview_dead_letter.identity,
        preview_dead_letter.intent_type,
        preview_dead_letter.attempt_count,
        preview_dead_letter.error_code,
        preview_dead_letter.failed_at,
        ProjectorDeadLetterSuccessor(
            20, 20, PreviewFingerprint("b" * 64), False
        ),
    )
    retry_port = _RetryPort(changed)
    application = _application(retry_port)
    request = _supersede_request(preview_dead_letter)

    with pytest.raises(ValueError, match="projector_dead_letter_successor_stale"):
        application.apply_dead_letter_supersede(request)

    assert retry_port.supersede_receipts == {}


@pytest.mark.parametrize(
    ("projector", "owner", "bindings", "row", "snapshot", "active"),
    (
        (
            "government_overpayment",
            "gov-1",
            {"overpayment_identity": "gov-1", "overpayment_version": 4},
            {
                "projection_version": 4,
                "status": "offset_reserved",
                "remaining_amount_ntd": 300,
            },
            {"amount_delta_ntd": 300},
            False,
        ),
        (
            "client_over_refund_recovery",
            "client-1",
            {
                "recovery_identity": "client-1",
                "recovery_version": 3,
                "case_no": "CASE-1",
                "account_version": 8,
            },
            {
                "projection_version": 3,
                "status": "partially_recovered",
                "remaining_amount_ntd": 200,
                "case_no": "CASE-1",
                "account_version": 8,
            },
            {"amount_delta_ntd": 200},
            True,
        ),
        (
            "staff_overpayment_recovery",
            "staff-1",
            {
                "recovery_identity": "staff-1",
                "recovery_version": 6,
                "staff_id": 12,
                "staff_payables_version": 9,
            },
            {
                "projection_version": 6,
                "status": "recovered",
                "remaining_amount_ntd": 0,
                "staff_id": 12,
                "staff_payables_version": 9,
            },
            {"amount_delta_ntd": 0},
            False,
        ),
    ),
)
def test_supersede_owner_readback_requires_exact_current_projection(
    projector, owner, bindings, row, snapshot, active
) -> None:
    assert _owner_projection_equivalent(
        projector, owner, row, bindings, snapshot, active
    )
    assert not _owner_projection_equivalent(
        projector,
        owner,
        row,
        bindings,
        {"amount_delta_ntd": snapshot["amount_delta_ntd"] + 1},
        active,
    )


def test_supersede_matching_readback_rejects_wrong_owner_or_version() -> None:
    bindings = {
        "matching_version": 3,
        "staff_id": 12,
    }
    exact = {
        "recovery_identity": "staff-1",
        "matching_version": 3,
        "staff_id": 12,
    }
    assert _matching_projection_equivalent(
        "staff_overpayment_recovery", "staff-1", exact, bindings
    )
    assert not _matching_projection_equivalent(
        "staff_overpayment_recovery",
        "staff-1",
        {**exact, "matching_version": 4},
        bindings,
    )


def test_http_preview_apply_contract_returns_only_safe_dead_letter_receipt() -> None:
    dead_letter = _dead_letter()
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    principal = AdminPrincipal(1, "system-admin", "System Admin", "system_admin")
    preview_response = preview_retry_route(
        RetryProjectorDeadLetterPreviewBody(
            reason="來源已由人工修正",
            evidence_reference="support-case:17",
        ),
        projector_identity="government_overpayment",
        event_id=17,
        principal=principal,
        application=application,
    )

    preview = preview_response.data
    apply_response = apply_projector_dead_letter_retry(
        RetryProjectorDeadLetterApplyBody(
            expected_attempt_count=preview["expected_attempt_count"],
            reason=preview["reason"],
            evidence_reference=preview["evidence_reference"],
            preview_fingerprint=preview["preview_fingerprint"],
        ),
        projector_identity="government_overpayment",
        event_id=17,
        idempotency_key="retry-http-17",
        correlation_header="retry-http-correlation-17",
        principal=principal,
        application=application,
    )

    assert apply_response.data == {
        "projector_identity": "government_overpayment",
        "event_id": 17,
        "prior_attempt_count": 3,
        "resulting_status": "pending",
        "receipt_identity": "anomaly-projector-retry:retry-http-17",
        "replayed": False,
    }
    assert "payload" not in str(apply_response.data).lower()


def test_http_supersede_contract_returns_verified_successor_receipt() -> None:
    dead_letter = _dead_letter(with_successor=True)
    retry_port = _RetryPort(dead_letter)
    application = _application(retry_port)
    principal = AdminPrincipal(1, "system-admin", "System Admin", "system_admin")
    preview_response = preview_supersede_route(
        RetryProjectorDeadLetterPreviewBody(
            reason="較高版本已投影",
            evidence_reference="incident:17",
        ),
        projector_identity="government_overpayment",
        event_id=17,
        principal=principal,
        application=application,
    )
    preview = preview_response.data
    apply_response = apply_projector_dead_letter_supersede(
        SupersedeProjectorDeadLetterApplyBody(
            expected_attempt_count=preview["expected_attempt_count"],
            expected_successor_event_id=preview["successor_event_id"],
            expected_successor_source_version=preview[
                "successor_source_version"
            ],
            reason=preview["reason"],
            evidence_reference=preview["evidence_reference"],
            preview_fingerprint=preview["preview_fingerprint"],
        ),
        projector_identity="government_overpayment",
        event_id=17,
        idempotency_key="supersede-http-17",
        correlation_header="supersede-http-correlation-17",
        principal=principal,
        application=application,
    )

    assert apply_response.data["successor_event_id"] == 19
    assert apply_response.data["resulting_status"] == (
        "superseded_by_verified_successor"
    )
    assert "payload" not in str(apply_response.data).lower()


@pytest.mark.parametrize(
    ("code", "status"),
    (
        ("projector_dead_letter_not_found", 404),
        ("projector_dead_letter_stale", 409),
        ("projector_dead_letter_preview_stale", 409),
        ("idempotency_conflict", 409),
        ("invalid reason", 422),
    ),
)
def test_http_error_preserves_safe_dead_letter_failure_semantics(code, status) -> None:
    error = _maintenance_contract_error(
        ValueError(code), CorrelationId("projector-retry-error")
    )

    assert isinstance(error, HTTPException)
    assert error.status_code == status
    assert error.detail["error"]["correlation_id"] == "projector-retry-error"
    assert "support-call" not in str(error.detail)
