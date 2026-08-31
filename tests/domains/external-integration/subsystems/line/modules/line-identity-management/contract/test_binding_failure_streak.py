"""Unique oracle for the bounded two-failure LINE identity streak."""

from __future__ import annotations

from datetime import datetime, timezone

from domains.line.identities import LineIdentityFlowId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    advance_binding_failure_streak,
    reset_binding_failure_streak,
)
from shared_kernel.identities import CorrelationId
from subsystems.line.identity_application import LineIdentityApplication


class _Identities:
    def __init__(self) -> None:
        self.current = None
        self.saves = 0

    def get_failure_streak(self, line_user_id, *, lock=False):
        assert lock is True
        return self.current

    def save_failure_streak(self, streak) -> None:
        self.current = streak
        self.saves += 1


class _CustomerService:
    def __init__(self) -> None:
        self.created = 0

    def create_or_append(self, command):
        self.created += 1
        return {"id": 9}


class _Escalations:
    def __init__(self) -> None:
        self.created = 0
        self.alerts = []
        self.events = []
        self.receipts = {}

    def get_by_idempotency(self, key, *, lock=False):
        return None

    def get_by_source(self, source, *, lock=False):
        return None

    def get_active_by_scope(self, scope, *, lock=False):
        return None

    def create(self, command, ticket):
        self.created += 1
        return {
            "id": 41,
            "ticket_id": ticket["id"],
            "workflow_status": "open",
            "workflow_version": 0,
            "hold_state": "active",
            "hold_version": 0,
            "ticket_version": 0,
        }

    def enqueue_masked_alert(self, intent) -> None:
        self.alerts.append(intent)

    def append_event(self, escalation_id, event_type, **values) -> None:
        self.events.append((escalation_id, event_type, values))

    def save_receipt(self, key, fingerprint, receipt) -> None:
        self.receipts[key] = (fingerprint, receipt)


class _UnitOfWork:
    def __init__(self, identities, customer_service, escalations) -> None:
        self.identities = identities
        self.customer_service = customer_service
        self.escalations = escalations
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1


def test_second_distinct_failure_creates_one_idempotent_customer_service_ticket() -> None:
    identities = _Identities()
    customer_service = _CustomerService()
    escalations = _Escalations()

    def factory():
        return _UnitOfWork(identities, customer_service, escalations)

    application = LineIdentityApplication(
        factory,
        lambda: datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    flow_id = LineIdentityFlowId("11111111-1111-1111-1111-111111111111")
    line_user_id = LineUserId("U-bounded-streak")

    application._record_binding_failure(
        flow_id,
        line_user_id,
        LineBindingSubjectType.CUSTOMER,
        "proof-scope-a",
        CorrelationId("failure-1"),
    )
    assert identities.current.failure_count == 1
    assert customer_service.created == 0

    application._record_binding_failure(
        flow_id,
        line_user_id,
        LineBindingSubjectType.CUSTOMER,
        "proof-scope-a",
        CorrelationId("failure-2"),
    )
    assert identities.current.failure_count == 2
    assert identities.current.escalation_id == 41
    assert customer_service.created == 1
    assert escalations.created == 1

    application._record_binding_failure(
        flow_id,
        line_user_id,
        LineBindingSubjectType.CUSTOMER,
        "proof-scope-a",
        CorrelationId("failure-2"),
    )
    assert identities.current.failure_count == 2
    assert customer_service.created == 1
    assert escalations.created == 1


def test_scope_change_replaces_count_and_success_reset_advances_generation() -> None:
    line_user_id = LineUserId("U-streak-generation")
    first, threshold = advance_binding_failure_streak(
        None,
        line_user_id=line_user_id,
        identity_flow_id="11111111-1111-1111-1111-111111111111",
        candidate_subject_type=LineBindingSubjectType.STAFF,
        candidate_scope="proof-scope-a",
        failure_identity="failure-a",
    )
    assert threshold is False
    changed, threshold = advance_binding_failure_streak(
        first,
        line_user_id=line_user_id,
        identity_flow_id="11111111-1111-1111-1111-111111111111",
        candidate_subject_type=LineBindingSubjectType.STAFF,
        candidate_scope="proof-scope-b",
        failure_identity="failure-b",
    )
    assert threshold is False
    assert changed.failure_count == 1
    assert changed.generation == first.generation + 1

    reset = reset_binding_failure_streak(
        changed,
        "11111111-1111-1111-1111-111111111111",
    )
    assert reset is not None
    assert reset.failure_count == 0
    assert reset.generation == changed.generation + 1
