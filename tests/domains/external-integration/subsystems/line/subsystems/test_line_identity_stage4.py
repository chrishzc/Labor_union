"""
File: test_line_identity_stage4.py
Description: 驗證 webhook identity entry、verified platform root、flow 與人工 review binding。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import (
    LineIdentityFlowId,
    LineReviewRequestId,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from domains.line.identity_flow import (
    LineIdentityFlowConflict,
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
)
from domains.line.platform_user import LineFriendStatus, LinePlatformUserSnapshot
from domains.line.review import (
    LineReviewDecision,
    LineReviewSnapshot,
    LineReviewStatus,
    LineReviewType,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.capabilities import LineCapability, LineCapabilityDeniedError
from subsystems.line.identity_application import LineIdentityApplication
from subsystems.line.identity_contracts import (
    LineIdentityCandidate,
    LineIdentityCommandOutcome,
    OpenLineIdentityFlowResult,
    StaffIdentityProof,
)
from subsystems.line.identity_review_application import (
    LineIdentityReviewApplication,
    LineReviewDataConflictError,
)
from subsystems.line.review_contracts import (
    CreateLineReviewResult,
    DecideLineReviewCommand,
    LineReviewCommandOutcome,
    PreviewLineReviewDecisionCommand,
)
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers

NOW = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)


class FakeUow:
    def __init__(self, **repositories) -> None:
        self.__dict__.update(repositories)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        self.committed = True


class RecordingRepository:
    def __init__(self) -> None:
        self.items = []

    def append(self, item):
        self.items.append(item)

    def enqueue(self, item):
        self.items.append(item)
        return item


def test_verified_liff_user_is_observed_before_identity_flow_open() -> None:
    operations = []

    class PlatformUsers:
        def ensure_verified_user(self, line_user_id):
            operations.append(("ensure_verified_user", line_user_id))
            return LinePlatformUserSnapshot(
                line_user_id,
                LineFriendStatus.UNKNOWN,
                ExpectedVersion(0),
            )

    class IdentityFlows:
        def open(self, command):
            assert operations == [("ensure_verified_user", command.line_user_id)]
            operations.append(("open_flow", command.line_user_id))
            return _opened_flow(command)

    uow = FakeUow(platform_users=PlatformUsers(), identity_flows=IdentityFlows())
    application = LineIdentityApplication(lambda: uow, lambda: NOW)

    result = application.open_flow(
        LineIdentityFlowPurpose.CUSTOMER_BINDING,
        LineUserId("U-verified"),
        IdempotencyKey("verified-flow:1"),
        CorrelationId("verified-flow:1"),
    )

    assert result.line_user_id == LineUserId("U-verified")
    assert operations == [
        ("ensure_verified_user", LineUserId("U-verified")),
        ("open_flow", LineUserId("U-verified")),
    ]
    assert uow.committed is True


def test_new_customer_flow_selects_dual_role_in_the_same_uow_and_replay_is_read_only() -> None:
    line_user_id = LineUserId("U-dual-role-flow")
    selected = [None]
    context_version = [ExpectedVersion(0)]
    bindings = (
        LineIdentityBindingSnapshot(
            line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(1),
            LineBindingSubjectType.CUSTOMER,
            "customer:23",
        ),
        LineIdentityBindingSnapshot(
            line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(1),
            LineBindingSubjectType.STAFF,
            "staff:18",
        ),
    )

    class Identities:
        def list_by_user(self, queried_line_user_id):
            assert queried_line_user_id == line_user_id
            return bindings

        def selected_role(self, queried_line_user_id):
            assert queried_line_user_id == line_user_id
            return selected[0], context_version[0]

        def select_role(self, queried_line_user_id, target_role, expected_version):
            assert queried_line_user_id == line_user_id
            assert expected_version == context_version[0]
            selected[0] = target_role
            context_version[0] = ExpectedVersion(expected_version.value + 1)
            return context_version[0]

    class FlowRepository:
        def __init__(self):
            self.calls = 0

        def open(self, command):
            self.calls += 1
            result = _opened_flow(command)
            if self.calls == 2:
                return OpenLineIdentityFlowResult(
                    result.flow_id,
                    result.purpose,
                    result.line_user_id,
                    result.expires_at,
                    LineIdentityCommandOutcome.EXISTING,
                )
            return result

    uow = FakeUow(
        platform_users=SimpleNamespace(ensure_verified_user=lambda _: None),
        identity_flows=FlowRepository(),
        identities=Identities(),
        receipts=ReceiptRepository(),
        audit=RecordingRepository(),
        outbox=RecordingRepository(),
    )
    application = LineIdentityApplication(lambda: uow, lambda: NOW)

    application.open_flow(
        LineIdentityFlowPurpose.CUSTOMER_BINDING,
        line_user_id,
        IdempotencyKey("dual-role-flow:1"),
        CorrelationId("dual-role-flow:1"),
    )
    application.open_flow(
        LineIdentityFlowPurpose.CUSTOMER_BINDING,
        line_user_id,
        IdempotencyKey("dual-role-flow:1"),
        CorrelationId("dual-role-flow:1"),
    )

    assert selected[0] is LineBindingSubjectType.CUSTOMER
    assert context_version[0] == ExpectedVersion(1)
    assert len(uow.receipts.items) == 1
    assert len(uow.audit.items) == 1
    assert len(uow.outbox.items) == 1
    assert uow.committed is True


def test_staff_command_only_opens_flow_and_queues_liff_link() -> None:
    flows = SimpleNamespace(open=lambda command: _opened_flow(command))
    deliveries = RecordingRepository()
    platform_events = []
    uow = FakeUow(
        platform_users=SimpleNamespace(apply_friend_event=platform_events.append),
        identity_flows=flows,
        delivery_tasks=deliveries,
    )
    handler = LineWebhookIdentityHandlers(
        lambda: NOW,
        lambda purpose, flow_id: f"https://example.test/{purpose}/{flow_id}",
    )

    handler.handle_message(_message_inbox("我是月嫂"), uow)

    assert platform_events[0].line_user_id == LineUserId("U-staff")
    assert len(deliveries.items) == 1
    assert "staff_verification" in deliveries.items[0].payload_json
    assert not hasattr(uow, "identities")


@pytest.mark.parametrize(
    ("message", "purpose"),
    [
        ("綁定", "customer_binding"),
        ("綁定訂單", "customer_binding"),
        ("訂單查詢", "customer_binding"),
        ("綁定工會帳號", "admin_binding"),
        ("綁定後台帳號", "admin_binding"),
        ("綁定system_admin", "admin_binding"),
    ],
)
def test_identity_commands_resolve_to_exact_flow(message, purpose) -> None:
    deliveries = RecordingRepository()
    uow = FakeUow(
        platform_users=SimpleNamespace(apply_friend_event=lambda _: None),
        identity_flows=SimpleNamespace(open=lambda command: _opened_flow(command)),
        delivery_tasks=deliveries,
    )
    handler = LineWebhookIdentityHandlers(
        lambda: NOW,
        lambda flow_purpose, flow_id: f"https://example.test/{flow_purpose}/{flow_id}",
    )

    handler.handle_message(_message_inbox(message), uow)

    assert purpose in deliveries.items[0].payload_json


def test_staff_apply_creates_manual_review_without_binding_owner() -> None:
    flow = _active_staff_flow()
    identities = PendingIdentityRepository()
    staff = StaffOwnerRepository()
    reviews = ReviewCreationRepository()
    deliveries = RecordingRepository()
    uow = FakeUow(
        identity_flows=FlowRepository(flow),
        identities=identities,
        staff=staff,
        reviews=reviews,
        delivery_tasks=deliveries,
    )
    application = LineIdentityApplication(lambda: uow, lambda: NOW)
    proof = StaffIdentityProof("王月嫂", "A123456789", date(1980, 1, 2))
    preview = application.preview_staff(flow.flow_id, flow.line_user_id, proof)

    result = application.apply_staff(
        flow.flow_id,
        flow.line_user_id,
        proof,
        preview.expected_version,
        preview.preview_fingerprint,
        CorrelationId("staff-application:1"),
    )

    assert result.review_request_id == LineReviewRequestId(41)
    assert staff.bind_calls == []
    assert identities.saved_claims[0].subject_type is LineBindingSubjectType.STAFF
    assert uow.committed is True
    assert len(deliveries.items) == 1


def test_validate_flow_rejects_expired_link_before_identity_form_is_shown() -> None:
    expired_flow = LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-expired"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        LineUserId("U-staff"),
        LineIdentityFlowStatus.ACTIVE,
        NOW,
        "staff-flow:expired",
    )
    application = LineIdentityApplication(
        lambda: FakeUow(identity_flows=FlowRepository(expired_flow)),
        lambda: NOW,
    )

    with pytest.raises(LineIdentityFlowConflict, match="expired"):
        application.validate_flow(
            expired_flow.flow_id,
            expired_flow.purpose,
            expired_flow.line_user_id,
        )


def test_review_approval_requires_capability_and_binds_in_one_uow() -> None:
    snapshot = _pending_staff_review()
    identities = ApprovalIdentityRepository(snapshot)
    staff = StaffOwnerRepository()
    reviews = ReviewDecisionRepository(snapshot)
    receipts = ReceiptRepository()
    uow = FakeUow(
        reviews=reviews,
        identities=identities,
        staff=staff,
        customers=SimpleNamespace(),
        admins=SimpleNamespace(),
        receipts=receipts,
        audit=RecordingRepository(),
        delivery_tasks=RecordingRepository(),
        outbox=RecordingRepository(),
    )
    application = LineIdentityReviewApplication(lambda: uow, lambda: NOW)
    command = _approve_command(LineCapability.IDENTITY_REVIEW.value)

    result = application.decide(command)

    assert result.snapshot.status is LineReviewStatus.APPROVED
    assert staff.bind_calls == [("12", LineUserId("U-staff"), None)]
    assert identities.bound is True
    assert reviews.decided is True
    assert receipts.items
    assert uow.committed is True

    denied = _approve_command()
    with pytest.raises(LineCapabilityDeniedError):
        application.decide(denied)


def test_review_decision_preview_is_zero_write_and_apply_rejects_stale_preview() -> None:
    snapshot = _pending_staff_review()
    uow = FakeUow(
        reviews=ReviewDecisionRepository(snapshot),
        identities=ApprovalIdentityRepository(snapshot),
        staff=StaffOwnerRepository(),
        customers=SimpleNamespace(),
        admins=SimpleNamespace(),
        receipts=ReceiptRepository(),
        audit=RecordingRepository(),
        delivery_tasks=RecordingRepository(),
        outbox=RecordingRepository(),
    )
    application = LineIdentityReviewApplication(lambda: uow, lambda: NOW)
    actor = ActorContext("admin:7", (LineCapability.IDENTITY_REVIEW.value,))

    preview = application.preview(
        PreviewLineReviewDecisionCommand(
            LineReviewRequestId(41),
            LineReviewDecision.APPROVE,
            ExpectedVersion(0),
            actor,
            "資料核對完成",
        )
    )

    assert preview.candidate.before_status is LineReviewStatus.PENDING
    assert preview.candidate.after_status is LineReviewStatus.APPROVED
    assert uow.committed is False

    stale = DecideLineReviewCommand(
        LineReviewRequestId(41),
        LineReviewDecision.APPROVE,
        ExpectedVersion(0),
        actor,
        "資料核對完成",
        fingerprint_payload({"stale": True}),
        IdempotencyKey("review-decision:stale"),
        CorrelationId("review:stale"),
    )
    with pytest.raises(LineReviewDataConflictError) as captured:
        application.decide(stale)

    assert captured.value.code == "line_review_preview_stale"
    assert uow.committed is False


def test_review_owner_drift_returns_specific_typed_conflict() -> None:
    snapshot = _pending_staff_review()
    uow = FakeUow(
        reviews=ReviewDecisionRepository(snapshot),
        identities=ApprovalIdentityRepository(snapshot),
        staff=ConflictingStaffOwnerRepository(),
        customers=SimpleNamespace(),
        admins=SimpleNamespace(),
        receipts=ReceiptRepository(),
        audit=RecordingRepository(),
        delivery_tasks=RecordingRepository(),
        outbox=RecordingRepository(),
    )
    application = LineIdentityReviewApplication(lambda: uow, lambda: NOW)

    with pytest.raises(LineReviewDataConflictError) as captured:
        application.decide(_approve_command(LineCapability.IDENTITY_REVIEW.value))

    assert captured.value.code == "staff_identity_binding_conflict"
    assert "月嫂目前綁定" in str(captured.value)
    assert uow.committed is False


class FlowRepository:
    def __init__(self, flow) -> None:
        self.flow = flow

    def get(self, _):
        return self.flow

    def consume(self, flow_id, purpose, line_user_id, _):
        assert (flow_id, purpose, line_user_id) == (
            self.flow.flow_id,
            self.flow.purpose,
            self.flow.line_user_id,
        )
        return self.flow


class PendingIdentityRepository:
    def __init__(self) -> None:
        self.saved_claims = []

    def get_by_subject(self, *_):
        return None

    def get(self, _, subject_type=None):
        assert subject_type in {None, LineBindingSubjectType.STAFF}
        return None

    def save_claim(self, claim, _):
        self.saved_claims.append(claim)
        return LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.PENDING_REVIEW,
            ExpectedVersion(1),
            claim.subject_type,
            claim.subject_reference,
        )


class StaffOwnerRepository:
    def __init__(self) -> None:
        self.bind_calls = []

    def resolve_staff(self, _):
        return LineIdentityCandidate(LineBindingSubjectType.STAFF, "12")

    def bind_staff(self, subject_reference, line_user_id, old_line_user_id):
        self.bind_calls.append((subject_reference, line_user_id, old_line_user_id))


class ConflictingStaffOwnerRepository(StaffOwnerRepository):
    def bind_staff(self, *_):
        raise RuntimeError("staff_identity_binding_conflict")


class ReviewCreationRepository:
    def create(self, command):
        snapshot = LineReviewSnapshot(
            LineReviewRequestId(41),
            command.review_type,
            LineReviewStatus.PENDING,
            ExpectedVersion(0),
            command.line_user_id,
            command.subject_type,
            command.subject_reference,
            command.request_fingerprint,
            command.evidence_json,
        )
        return CreateLineReviewResult(LineReviewCommandOutcome.CREATED, snapshot)


class ApprovalIdentityRepository:
    def __init__(self, review) -> None:
        self.pending = LineIdentityBindingSnapshot(
            review.line_user_id,
            LineIdentityBindingStatus.PENDING_REVIEW,
            ExpectedVersion(1),
            review.subject_type,
            review.subject_reference,
        )
        self.bound = False

    def get_by_subject(self, *_):
        return self.pending

    def get(self, _, subject_type=None):
        assert subject_type in {None, LineBindingSubjectType.STAFF}
        return self.pending

    def list_by_user(self, _):
        if not self.bound:
            return (self.pending,)
        return (
            LineIdentityBindingSnapshot(
                self.pending.line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(2),
                self.pending.subject_type,
                self.pending.subject_reference,
            ),
        )

    def bind(self, claim, expected_version, *_):
        assert expected_version == ExpectedVersion(1)
        self.bound = True
        return LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(2),
            claim.subject_type,
            claim.subject_reference,
        )


class ReviewDecisionRepository:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot
        self.decided = False

    def get(self, _):
        return self.snapshot

    def decide(self, *_):
        self.decided = True


class ReceiptRepository(RecordingRepository):
    def get(self, _):
        return None


def _opened_flow(command):
    return OpenLineIdentityFlowResult(
        LineIdentityFlowId("flow-staff"),
        command.purpose,
        command.line_user_id,
        command.expires_at,
        LineIdentityCommandOutcome.CREATED,
    )


def _message_inbox(text):
    source = SimpleNamespace(user_id=LineUserId("U-staff"))
    event = SimpleNamespace(
        event_id=LineWebhookEventId("event-staff"),
        source=source,
        occurred_at=NOW,
        payload_json=json.dumps({"message": {"type": "text", "text": text}}),
    )
    return SimpleNamespace(event=event)


def _active_staff_flow():
    return LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-staff"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        LineUserId("U-staff"),
        LineIdentityFlowStatus.ACTIVE,
        NOW + timedelta(minutes=15),
        "staff-flow:1",
    )


def _pending_staff_review():
    return LineReviewSnapshot(
        LineReviewRequestId(41),
        LineReviewType.STAFF_VERIFICATION,
        LineReviewStatus.PENDING,
        ExpectedVersion(0),
        LineUserId("U-staff"),
        LineBindingSubjectType.STAFF,
        "12",
        fingerprint_payload({"review": 41}),
    )


def _approve_command(*capabilities):
    return DecideLineReviewCommand(
        LineReviewRequestId(41),
        LineReviewDecision.APPROVE,
        ExpectedVersion(0),
        ActorContext("admin:7", tuple(sorted(capabilities))),
        "資料核對完成",
        fingerprint_payload(
            {
                "request_id": 41,
                "review_type": "staff_verification",
                "decision": "approve",
                "expected_version": 0,
                "actor_id": "admin:7",
                "reason": "資料核對完成",
            }
        ),
        IdempotencyKey("review-decision:41"),
        CorrelationId("review:41"),
    )
