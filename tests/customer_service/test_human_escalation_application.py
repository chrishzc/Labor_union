"""
File: test_human_escalation_application.py
Description: 驗證 M4 escalation 原子流程、重播、hold gate 與 caller-owned UoW gateway。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.customer_service.escalation import (
    AutomationHoldState,
    EscalationWorkflowStatus,
    HumanEscalationDomainError,
    MaskedContext,
    TriggerCode,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.customer_service.escalation_application import HumanEscalationApplication
from subsystems.customer_service.escalation_contracts import (
    ClaimHumanEscalation,
    CreateHumanEscalation,
    HumanEscalationError,
    ResolveHumanEscalation,
    StartHumanEscalationHandling,
)


_NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)
_SOURCE_DIGEST = "a" * 64


class _TicketPort:
    def __init__(self) -> None:
        self.next_id = 20
        self.rows: dict[int, dict[str, object]] = {}

    def create_or_append_escalation_ticket(self, command):
        self.next_id += 1
        row = {
            "id": self.next_id,
            "status": CustomerServiceStatus.WAITING,
            "version": 0,
            "category": command.ticket_category,
        }
        self.rows[self.next_id] = row
        return row

    def get(self, ticket_id: int, *, lock: bool = False):
        return self.rows[ticket_id]

    def start_handling_for_escalation(self, ticket_id: int, expected_version: int, actor_id: str):
        row = self.rows[ticket_id]
        assert row["version"] == expected_version
        row["status"] = CustomerServiceStatus.HANDLING
        row["version"] = expected_version + 1
        row["actor_id"] = actor_id
        return row

    def resolve_for_escalation(self, ticket_id: int, expected_version: int, actor_id: str, resolution_code: str):
        row = self.rows[ticket_id]
        assert row["version"] == expected_version
        row["status"] = CustomerServiceStatus.RESOLVED
        row["version"] = expected_version + 1
        row["actor_id"] = actor_id
        row["resolution_code"] = resolution_code
        return row


class _EscalationRepo:
    def __init__(self) -> None:
        self.rows: dict[int, dict[str, object]] = {}
        self.receipts: dict[str, dict[str, object]] = {}
        self.events: list[tuple[int, object, dict[str, object]]] = []
        self.alerts = []
        self.next_id = 0

    def get_by_id(self, escalation_id: int, *, lock: bool = False):
        return self.rows.get(escalation_id)

    def get_by_source(self, source_event_identity: str, *, lock: bool = False):
        return next((row for row in self.rows.values() if row["source_event_identity"] == source_event_identity), None)

    def get_by_idempotency(self, key: str, *, lock: bool = False):
        return self.receipts.get(key)

    def get_active_by_scope(self, hold_scope: str, *, lock: bool = False):
        return next(
            (
                row
                for row in self.rows.values()
                if row["hold_scope"] == hold_scope and row["hold_state"] == AutomationHoldState.ACTIVE.value
            ),
            None,
        )

    def create(self, command, ticket):
        self.next_id += 1
        row = {
            "id": self.next_id,
            "ticket_id": ticket["id"],
            "ticket_category": command.ticket_category,
            "source_event_identity": command.source_event_identity,
            "source_fingerprint": command.source_fingerprint,
            "trigger_code": command.trigger_code,
            "masked_context": command.masked_context.as_dict(),
            "hold_scope": command.hold_scope,
            "workflow_status": EscalationWorkflowStatus.OPEN.value,
            "workflow_version": 0,
            "hold_state": AutomationHoldState.ACTIVE.value,
            "hold_version": 0,
            "ticket_version": int(ticket["version"]),
            "alert_status": "queued",
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        self.rows[self.next_id] = row
        return row

    def transition(self, escalation_id: int, **changes):
        row = self.rows[escalation_id]
        row.update(changes)
        row["updated_at"] = _NOW
        return row

    def append_event(self, escalation_id: int, event_type, **values):
        self.events.append((escalation_id, event_type, values))

    def append_source_event(self, escalation_id: int, command):
        self.events.append((escalation_id, "source_appended", {"source_event_identity": command.source_event_identity}))

    def enqueue_masked_alert(self, intent):
        self.alerts.append(intent)

    def save_receipt(self, key: str, fingerprint: str, receipt):
        row = self.rows[receipt.escalation_id]
        self.receipts[key] = {
            **row,
            "request_fingerprint": fingerprint,
            "receipt": receipt,
            "correlation_id": receipt.correlation_id,
        }

    def active_hold(self, hold_scope: str):
        row = self.get_active_by_scope(hold_scope)
        if row is None:
            return None
        from subsystems.customer_service.escalation_contracts import AutomationHoldDecision

        return AutomationHoldDecision(AutomationHoldState.ACTIVE, hold_scope)


class _Source:
    def __init__(self, can_release: bool = True) -> None:
        self.allowed = can_release

    def can_release(self, escalation) -> bool:
        return self.allowed


class _Uow:
    def __init__(self, repo, tickets, source):
        self.escalations = repo
        self.customer_service = tickets
        self.escalation_source = source
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self):
        self.committed = True


def _command(key: str = "create-1") -> CreateHumanEscalation:
    from domains.customer_service.escalation import MaskedContext

    return CreateHumanEscalation(
        source_event_identity="line-event-1",
        source_kind="line_inbox",
        source_fingerprint=_SOURCE_DIGEST,
        trigger_code=TriggerCode.COMPLAINT,
        trigger_policy_version="complaint.v1",
        ticket_category=CustomerServiceCategory.OTHER,
        masked_context=MaskedContext("complaint_explicit", "complaint.v1", "other", "m4-mask.v1"),
        hold_scope="conversation:opaque",
        idempotency_key=IdempotencyKey(key),
        correlation_id=CorrelationId(f"corr-{key}"),
        actor=ActorContext("system:m4"),
    )


def _app(repo, tickets, source):
    return HumanEscalationApplication(lambda: _Uow(repo, tickets, source), now=lambda: _NOW)


def test_create_preview_is_zero_write_and_apply_requires_matching_fingerprint():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    app = _app(repo, tickets, source)
    command = _command("create-preview-1")

    preview = app.preview(command)

    assert preview.operation == "create"
    assert preview.escalation_id is None
    assert preview.before_workflow_status == "absent"
    assert preview.resulting_workflow_status is EscalationWorkflowStatus.OPEN
    assert preview.before_hold_state == "absent"
    assert preview.resulting_hold_state is AutomationHoldState.ACTIVE
    assert preview.apply_ready is True
    assert repo.rows == {}
    assert repo.receipts == {}
    assert repo.events == []
    assert repo.alerts == []
    assert tickets.rows == {}

    with pytest.raises(HumanEscalationError) as mismatch:
        app.create(replace(command, preview_fingerprint=PreviewFingerprint("0" * 64)))
    assert mismatch.value.code == "human_escalation_preview_conflict"
    assert repo.rows == {}
    assert tickets.rows == {}

    receipt = app.create(replace(command, preview_fingerprint=preview.preview_fingerprint))
    assert receipt.resulting_workflow_status is EscalationWorkflowStatus.OPEN
    assert len(repo.rows) == 1
    assert len(tickets.rows) == 1


def test_complaint_resolve_uses_customer_service_handling_evidence_not_runtime_gate():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(False)
    app = _app(repo, tickets, source)
    created = app.create(_command())
    assert created.resulting_workflow_status is EscalationWorkflowStatus.OPEN
    assert created.resulting_hold_state is AutomationHoldState.ACTIVE
    assert len(repo.alerts) == 1
    claimed = app.claim(ClaimHumanEscalation(created.escalation_id, 0, ActorContext("admin:1"), IdempotencyKey("claim-1"), CorrelationId("corr-claim")))
    handling = app.start_handling(StartHumanEscalationHandling(created.escalation_id, 1, 0, ActorContext("admin:1"), IdempotencyKey("handling-1"), CorrelationId("corr-handling")))
    resolved = app.resolve(ResolveHumanEscalation(created.escalation_id, 2, 1, "handled", _SOURCE_DIGEST, ActorContext("admin:1"), IdempotencyKey("resolve-1"), CorrelationId("corr-resolve")))
    assert claimed.resulting_workflow_status is EscalationWorkflowStatus.CLAIMED
    assert handling.resulting_workflow_status is EscalationWorkflowStatus.HANDLING
    assert resolved.resulting_workflow_status is EscalationWorkflowStatus.RESOLVED
    assert resolved.resulting_hold_state is AutomationHoldState.RELEASED
    assert [event.value for _, event, _ in repo.events] == ["created", "claimed", "handling_started", "resolved", "hold_released"]


def test_resolve_keeps_hold_active_when_source_predicate_is_not_satisfied():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(False)
    app = _app(repo, tickets, source)
    base = _command()
    created = app.create(
        CreateHumanEscalation(
            source_event_identity="runtime-event-1",
            source_kind="runtime_health",
            source_fingerprint=base.source_fingerprint,
            trigger_code=TriggerCode.RUNTIME_CRITICAL,
            trigger_policy_version="runtime-critical.v1",
            ticket_category=base.ticket_category,
            masked_context=MaskedContext(
                "runtime_critical",
                "runtime-critical.v1",
                "other",
                "m4-mask.v1",
            ),
            hold_scope="capability:line_delivery",
            idempotency_key=IdempotencyKey("create-runtime-1"),
            correlation_id=CorrelationId("corr-create-runtime-1"),
            actor=base.actor,
        )
    )
    app.claim(ClaimHumanEscalation(created.escalation_id, 0, ActorContext("admin:1"), IdempotencyKey("claim-2"), CorrelationId("corr-claim-2")))
    app.start_handling(StartHumanEscalationHandling(created.escalation_id, 1, 0, ActorContext("admin:1"), IdempotencyKey("handling-2"), CorrelationId("corr-handling-2")))
    with pytest.raises(HumanEscalationError) as exc:
        app.resolve(ResolveHumanEscalation(created.escalation_id, 2, 1, "handled", _SOURCE_DIGEST, ActorContext("admin:1"), IdempotencyKey("resolve-2"), CorrelationId("corr-resolve-2")))
    assert exc.value.code == "automation_hold_release_blocked"
    assert repo.rows[created.escalation_id]["hold_state"] == AutomationHoldState.ACTIVE.value


def test_active_hold_guard_blocks_automation_and_missing_repository_fails_closed():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    app = _app(repo, tickets, source)
    app.create(_command())
    with pytest.raises(HumanEscalationError) as exc:
        app.hold_guard("conversation:opaque")
    assert exc.value.code == "automation_hold_active"

    class _NoRepoUow(_Uow):
        def __init__(self):
            self.escalations = None
            self.customer_service = tickets
            self.escalation_source = source

    guarded = HumanEscalationApplication(_NoRepoUow)
    with pytest.raises(HumanEscalationError) as missing:
        guarded.hold_guard("conversation:opaque")
    assert missing.value.code == "human_escalation_persistence_unavailable"


def test_same_idempotency_payload_replays_without_duplicate_alert():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    app = _app(repo, tickets, source)
    first = app.create(_command())
    replay = app.create(_command())
    assert first.escalation_id == replay.escalation_id
    assert replay.replayed is True
    assert replay.committed_at == first.committed_at
    assert len(repo.rows) == 1
    assert len(repo.alerts) == 1


def test_stale_transition_is_typed_conflict():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    app = _app(repo, tickets, source)
    created = app.create(_command("create-stale"))
    with pytest.raises(HumanEscalationError) as exc:
        app.claim(ClaimHumanEscalation(created.escalation_id, 9, ActorContext("admin:1"), IdempotencyKey("claim-stale"), CorrelationId("corr-stale")))
    assert exc.value.category == "conflict"
    assert exc.value.code == "human_escalation_version_conflict"


def test_masked_context_rejects_phone_email_and_line_user_id_values():
    for unsafe in ("0912-345-678", "member@example.test", "U" + "a" * 32):
        with pytest.raises(HumanEscalationDomainError):
            MaskedContext(unsafe, "complaint.v1", "other", "m4-mask.v1")


def test_active_scope_appends_source_and_saves_replay_receipt_without_new_alert():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    app = _app(repo, tickets, source)
    first = app.create(_command("create-scope-1"))
    second_command = _command("create-scope-2")
    second_command = CreateHumanEscalation(
        source_event_identity="line-event-2",
        source_kind=second_command.source_kind,
        source_fingerprint="b" * 64,
        trigger_code=second_command.trigger_code,
        trigger_policy_version=second_command.trigger_policy_version,
        ticket_category=second_command.ticket_category,
        masked_context=second_command.masked_context,
        hold_scope=second_command.hold_scope,
        idempotency_key=second_command.idempotency_key,
        correlation_id=second_command.correlation_id,
        actor=second_command.actor,
    )
    appended = app.create(second_command)
    replayed = app.create(second_command)
    assert appended.escalation_id == first.escalation_id
    assert replayed.replayed is True
    assert len(repo.rows) == 1
    assert len(repo.alerts) == 1
    assert [event for _, event, _ in repo.events].count("source_appended") == 1


def test_create_for_ticket_uses_precreated_ticket_and_caller_owned_uow_without_commit():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    command = _command("create-existing-uow")
    ticket = tickets.create_or_append_escalation_ticket(command)
    existing_uow = _Uow(repo, tickets, source)
    app = HumanEscalationApplication(lambda: pytest.fail("gateway must not create another UoW"), now=lambda: _NOW)

    receipt = app.create_for_ticket(command, ticket, existing_uow)

    assert receipt.escalation_id == 1
    assert repo.rows[1]["ticket_id"] == ticket["id"]
    assert len(repo.events) == 1
    assert len(repo.receipts) == 1
    assert len(repo.alerts) == 1
    assert existing_uow.committed is False


def test_hold_guard_uses_caller_owned_uow_and_returns_stable_active_error():
    repo, tickets, source = _EscalationRepo(), _TicketPort(), _Source(True)
    command = _command("create-hold-existing-uow")
    ticket = tickets.create_or_append_escalation_ticket(command)
    repo.create(command, ticket)
    existing_uow = _Uow(repo, tickets, source)
    app = HumanEscalationApplication(lambda: pytest.fail("gateway must not create another UoW"), now=lambda: _NOW)

    with pytest.raises(HumanEscalationError) as raised:
        app.hold_guard(command.hold_scope, existing_uow)

    assert raised.value.code == "automation_hold_active"
    assert existing_uow.committed is False
