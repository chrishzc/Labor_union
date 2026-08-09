"""Stage 4 workflow tests for webhook identity entry and human review."""

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
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
)
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
from subsystems.line.identity_review_application import LineIdentityReviewApplication
from subsystems.line.review_contracts import (
    CreateLineReviewResult,
    DecideLineReviewCommand,
    LineReviewCommandOutcome,
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

    result = application.apply_staff(
        flow.flow_id,
        flow.line_user_id,
        StaffIdentityProof("王月嫂", "A123456789", date(1980, 1, 2)),
        CorrelationId("staff-application:1"),
    )

    assert result.review_request_id == LineReviewRequestId(41)
    assert staff.bind_calls == []
    assert identities.saved_claims[0].subject_type is LineBindingSubjectType.STAFF
    assert uow.committed is True
    assert len(deliveries.items) == 1


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

    def get(self, _):
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

    def get(self, _):
        return self.pending

    def bind(self, claim, expected_version, *_):
        assert expected_version == ExpectedVersion(1)
        self.bound = True
        return self.pending


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
        IdempotencyKey("review-decision:41"),
        CorrelationId("review:41"),
    )
