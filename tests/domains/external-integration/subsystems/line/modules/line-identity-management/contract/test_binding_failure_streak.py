"""Unique oracle for the bounded two-failure LINE identity streak."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domains.line.identities import LineIdentityFlowId, LineUserId
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
)
from domains.line.identity_binding import (
    LineBindingSubjectType,
    advance_binding_failure_streak,
    reset_binding_failure_streak,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.line.identity_application import LineIdentityApplication, LineIdentityNotFoundError
from subsystems.line.identity_contracts import CustomerIdentityProof
from api.routes.customer_service import _escalation_view_response
from subsystems.customer_service.escalation_application import _view


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

    def enqueue_alert(self, intent) -> None:
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


def test_apply_customer_identity_mismatch_escalates_once_and_readback_is_typed() -> None:
    """Exercise the real Apply ingress, not just the private streak recorder."""

    line_user_id = LineUserId("U-gateway-ingress")
    flow_id = LineIdentityFlowId("22222222-2222-2222-2222-222222222222")
    proof = CustomerIdentityProof("wrong name", "0900000000")
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    state = {"streak": None, "ticket_creates": 0, "escalations": 0, "row": None}

    class Flows:
        def get(self, requested):
            assert requested == flow_id
            return LineIdentityFlowSnapshot(
                flow_id, LineIdentityFlowPurpose.CUSTOMER_BINDING, line_user_id,
                LineIdentityFlowStatus.ACTIVE, datetime(2026, 8, 31, tzinfo=timezone.utc),
                "gateway-flow", 0,
            )

    class Customers:
        def resolve_customer(self, requested):
            assert requested == proof
            return None

    class Identities:
        def get(self, requested, subject_type, *args, **kwargs):
            assert requested == line_user_id
            return None

        def get_failure_streak(self, requested, *, lock=False):
            assert requested == line_user_id and lock is True
            return state["streak"]

        def save_failure_streak(self, streak):
            state["streak"] = streak

    class CustomerService:
        def create_or_append(self, command):
            state["ticket_creates"] += 1
            return {"id": 77}

    class Escalations:
        def get_by_idempotency(self, key, *, lock=False):
            return None

        def get_by_source(self, source, *, lock=False):
            return None

        def get_active_by_scope(self, scope, *, lock=False):
            return None

        def create(self, command, ticket):
            state["escalations"] += 1
            state["row"] = {
                "id": 88,
                "ticket_id": ticket["id"],
                "source_event_identity": command.source_event_identity,
                "ticket_category": command.ticket_category,
                "trigger_code": command.trigger_code,
                "workflow_status": "open",
                "workflow_version": 0,
                "hold_state": "active",
                "hold_version": 0,
                "context": command.context.as_dict(),
                "alert_status": "pending",
                "created_at": now,
                "updated_at": now,
            }
            return state["row"]

        def enqueue_alert(self, intent):
            return None

        def append_event(self, *args, **kwargs):
            return None

        def save_receipt(self, *args, **kwargs):
            return None

    class Uow:
        def __init__(self):
            self.identity_flows = Flows()
            self.customers = Customers()
            self.identities = Identities()
            self.customer_service = CustomerService()
            self.escalations = Escalations()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def commit(self):
            return None

    application = LineIdentityApplication(lambda: Uow(), lambda: now)
    for correlation in ("gateway-attempt-1", "gateway-attempt-2"):
        preview = application.preview_customer(flow_id, line_user_id, proof)
        assert preview.status.value == "not_found"
        with pytest.raises(LineIdentityNotFoundError):
            application.apply_customer(
                flow_id, line_user_id, proof, ExpectedVersion(0),
                preview.preview_fingerprint, CorrelationId(correlation),
            )

    preview = application.preview_customer(flow_id, line_user_id, proof)
    with pytest.raises(LineIdentityNotFoundError):
        application.apply_customer(
            flow_id, line_user_id, proof, ExpectedVersion(0),
            preview.preview_fingerprint, CorrelationId("gateway-attempt-2"),
        )

    assert state["streak"].failure_count == 2
    assert state["ticket_creates"] == 1
    assert state["escalations"] == 1
    readback = _escalation_view_response(_view(state["row"]))
    assert readback.trigger_identity.startswith("binding-failure:")
    assert readback.attempt_window is not None
    assert readback.attempt_window.attempt_count == 2
    assert readback.attempt_window.maximum_attempts == 2
    assert readback.owner_selector == "customer_service.ticket_owner"
    assert set(readback.context) == {
        "summary_code", "policy_version", "category", "redaction_version",
    }
    serialized = str(readback.model_dump())
    assert "wrong name" not in serialized
    assert "U-gateway-ingress" not in serialized
    assert "0900000000" not in serialized
