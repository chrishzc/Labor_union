"""File: escalation_application.py
Description: M4 escalation create、claim、handling、resolve、hold 與 caller-owned UoW 原子流程。
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import fields, replace
import hashlib
import re
from typing import Callable, Iterable, Mapping

from domains.customer_service.escalation import (
    AlertStatus,
    AutomationHoldState,
    EscalationEventType,
    EscalationWorkflowStatus,
    HumanEscalationDomainError,
    MaskedAlertIntent,
    MaskedContext,
    TriggerCode,
)
from domains.customer_service.ticket import CustomerServiceStatus, transition_ticket
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.customer_service.escalation_contracts import (
    AutomationHoldDecision,
    ClaimHumanEscalation,
    CreateHumanEscalation,
    HumanEscalationError,
    HumanEscalationPreview,
    HumanEscalationReceipt,
    HumanEscalationView,
    HumanEscalationAttemptWindow,
    ResolveHumanEscalation,
    StartHumanEscalationHandling,
)


_FAMILY = "customer_service_human_escalation"


class HumanEscalationApplication:
    def __init__(self, unit_of_work_factory: Callable[[], object], now: Callable[[], datetime] | None = None) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create(self, command: CreateHumanEscalation) -> HumanEscalationReceipt:
        with self._unit_of_work_factory() as uow:
            receipt, should_commit = self._create(command, uow)
            if should_commit:
                uow.commit()
            return receipt

    def preview(self, command) -> HumanEscalationPreview:
        with self._unit_of_work_factory() as uow:
            snapshot = _preview_snapshot(uow, command, lock=False)
            return HumanEscalationPreview(
                operation=snapshot["operation"],
                escalation_id=snapshot["escalation_id"],
                before_workflow_status=snapshot["before_workflow_status"],
                resulting_workflow_status=EscalationWorkflowStatus(snapshot["resulting_workflow_status"]),
                before_hold_state=snapshot["before_hold_state"],
                resulting_hold_state=AutomationHoldState(snapshot["resulting_hold_state"]),
                current_escalation_version=snapshot["current_escalation_version"],
                current_ticket_version=snapshot["current_ticket_version"],
                preview_fingerprint=_preview_fingerprint(command, snapshot),
                apply_ready=True,
            )

    def create_for_ticket(self, command: CreateHumanEscalation, ticket: object, unit_of_work: object) -> HumanEscalationReceipt:
        receipt, _ = self._create(command, unit_of_work, ticket)
        return receipt

    def _create(self, command: CreateHumanEscalation, uow: object, ticket: object | None = None) -> tuple[HumanEscalationReceipt, bool]:
        fingerprint = _command_fingerprint(command)
        repo = _repo(uow)
        existing = _call(repo, "get_by_idempotency", command.idempotency_key.value, lock=True)
        if existing is not None:
            return self._replay_or_conflict(repo, existing, fingerprint, command.correlation_id.value, "create"), False
        _verify_preview(uow, command)
        source = _call(repo, "get_by_source", command.source_event_identity, lock=True)
        if source is not None:
            if _field(source, "source_fingerprint") != command.source_fingerprint:
                raise _error("conflict", "human_escalation_source_conflict")
            return self._replay_or_conflict(repo, source, fingerprint, command.correlation_id.value, "create"), False
        active = _call(repo, "get_active_by_scope", command.hold_scope, lock=True)
        if active is not None:
            append = getattr(repo, "append_source_event", None)
            if append is None:
                raise _error("conflict", "human_escalation_duplicate_scope_active")
            try:
                append(_field(active, "id"), command)
            except Exception as error:
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True) from error
            receipt = self._receipt(active, "create", command.correlation_id.value, replayed=False)
            repo.save_receipt(command.idempotency_key.value, fingerprint, receipt)
            return receipt, True
        try:
            if ticket is None:
                ticket_port = getattr(uow, "customer_service", None)
                if ticket_port is None or not hasattr(ticket_port, "create_or_append_escalation_ticket"):
                    raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
                ticket = ticket_port.create_or_append_escalation_ticket(command)
            escalation = repo.create(command, ticket)
            intent = _intent(escalation, ticket, command)
            repo.enqueue_masked_alert(intent)
            repo.append_event(
                int(_field(escalation, "id")), EscalationEventType.CREATED,
                expected_escalation_version=0, resulting_escalation_version=int(_field(escalation, "workflow_version", 0)),
                expected_hold_version=0, resulting_hold_version=int(_field(escalation, "hold_version", 0)),
                actor_ref=command.actor.actor_id, reason_code=command.trigger_code.value,
                reason_evidence_digest=command.source_fingerprint,
                receipt_id=_receipt_id("create", command.idempotency_key.value),
                idempotency_key=command.idempotency_key.value, correlation_id=command.correlation_id.value,
            )
            receipt = self._receipt(escalation, "create", command.correlation_id.value, replayed=False)
            repo.save_receipt(command.idempotency_key.value, fingerprint, receipt)
            return receipt, True
        except HumanEscalationError:
            raise
        except LookupError as error:
            raise _error("not_found", "human_escalation_not_found") from error
        except Exception as error:
            code = "human_escalation_outbox_unavailable" if "alert" in str(error).lower() or "outbox" in str(error).lower() else "human_escalation_persistence_unavailable"
            raise _error("unavailable", code, retryable=True) from error

    def claim(self, command: ClaimHumanEscalation) -> HumanEscalationReceipt:
        return self._transition(command, EscalationEventType.CLAIMED, EscalationWorkflowStatus.OPEN, EscalationWorkflowStatus.CLAIMED)

    def start_handling(self, command: StartHumanEscalationHandling) -> HumanEscalationReceipt:
        with self._unit_of_work_factory() as uow:
            repo = _repo(uow)
            fingerprint = _command_fingerprint(command)
            replay = _replay_receipt(repo, command.idempotency_key.value, fingerprint)
            if replay is not None:
                return replay
            _verify_preview(uow, command)
            escalation = _load(repo, command.escalation_id)
            _check_version(escalation, command.expected_escalation_version)
            _check_state(escalation, EscalationWorkflowStatus.CLAIMED)
            ticket = _ticket(uow, escalation, lock=True)
            if int(_field(ticket, "version")) != command.expected_ticket_version:
                raise _error("conflict", "human_escalation_version_conflict")
            transition = getattr(getattr(uow, "customer_service", None), "start_handling_for_escalation", None)
            if transition is None:
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
            try:
                updated_ticket = transition(int(_field(escalation, "ticket_id")), command.expected_ticket_version, command.actor.actor_id)
                if _field(updated_ticket, "status") is not CustomerServiceStatus.HANDLING and str(_field(updated_ticket, "status")) != CustomerServiceStatus.HANDLING.value:
                    raise _error("domain_blocked", "human_escalation_transition_invalid")
                updated = repo.transition(int(_field(escalation, "id")), workflow_status=EscalationWorkflowStatus.HANDLING.value, workflow_version=command.expected_escalation_version + 1, ticket_version=int(_field(updated_ticket, "version")))
                receipt = self._receipt(updated, "handling_started", command.correlation_id.value, replayed=False)
                repo.append_event(int(_field(escalation, "id")), EscalationEventType.HANDLING_STARTED, expected_escalation_version=command.expected_escalation_version, resulting_escalation_version=command.expected_escalation_version + 1, expected_ticket_version=command.expected_ticket_version, resulting_ticket_version=int(_field(updated_ticket, "version")), expected_hold_version=int(_field(escalation, "hold_version", 0)), resulting_hold_version=int(_field(escalation, "hold_version", 0)), actor_ref=command.actor.actor_id, reason_code="handling_started", reason_evidence_digest=_digest(command), receipt_id=_receipt_id("handling_started", command.idempotency_key.value), idempotency_key=command.idempotency_key.value, correlation_id=command.correlation_id.value)
                repo.save_receipt(command.idempotency_key.value, fingerprint, receipt)
                uow.commit()
                return receipt
            except HumanEscalationError:
                raise
            except Exception as error:
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True) from error

    def resolve(self, command: ResolveHumanEscalation) -> HumanEscalationReceipt:
        with self._unit_of_work_factory() as uow:
            repo = _repo(uow)
            fingerprint = _command_fingerprint(command)
            replay = _replay_receipt(repo, command.idempotency_key.value, fingerprint)
            if replay is not None:
                return replay
            _verify_preview(uow, command)
            escalation = _load(repo, command.escalation_id)
            _check_version(escalation, command.expected_escalation_version)
            _check_state(escalation, EscalationWorkflowStatus.HANDLING)
            ticket = _ticket(uow, escalation, lock=True)
            if int(_field(ticket, "version")) != command.expected_ticket_version:
                raise _error("conflict", "human_escalation_version_conflict")
            ticket_status = _field(ticket, "status")
            if (
                ticket_status is not CustomerServiceStatus.HANDLING
                and str(ticket_status) != CustomerServiceStatus.HANDLING.value
            ):
                raise _error("domain_blocked", "automation_hold_release_blocked")
            source = getattr(uow, "escalation_source", None)
            if not _release_predicate_satisfied(escalation, source):
                raise _error("domain_blocked", "automation_hold_release_blocked")
            ticket_port = getattr(uow, "customer_service", None)
            resolve_ticket = getattr(ticket_port, "resolve_for_escalation", None)
            if resolve_ticket is None:
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
            try:
                resolved_ticket = resolve_ticket(int(_field(escalation, "ticket_id")), command.expected_ticket_version, command.actor.actor_id, command.resolution_code)
                status = _field(resolved_ticket, "status")
                if status is not CustomerServiceStatus.RESOLVED and str(status) != CustomerServiceStatus.RESOLVED.value:
                    raise _error("domain_blocked", "automation_hold_release_blocked")
                updated = repo.transition(int(_field(escalation, "id")), workflow_status=EscalationWorkflowStatus.RESOLVED.value, workflow_version=command.expected_escalation_version + 1, hold_state=AutomationHoldState.RELEASED.value, hold_version=int(_field(escalation, "hold_version", 0)) + 1, ticket_version=int(_field(resolved_ticket, "version")), resolution_code=command.resolution_code, resolution_evidence_digest=command.resolution_evidence_digest)
                receipt = self._receipt(updated, "resolve", command.correlation_id.value, replayed=False)
                for event_type in (EscalationEventType.RESOLVED, EscalationEventType.HOLD_RELEASED):
                    repo.append_event(int(_field(escalation, "id")), event_type, expected_escalation_version=command.expected_escalation_version, resulting_escalation_version=command.expected_escalation_version + 1, expected_ticket_version=command.expected_ticket_version, resulting_ticket_version=int(_field(resolved_ticket, "version")), expected_hold_version=int(_field(escalation, "hold_version", 0)), resulting_hold_version=int(_field(escalation, "hold_version", 0)) + 1, actor_ref=command.actor.actor_id, reason_code=command.resolution_code, reason_evidence_digest=command.resolution_evidence_digest, receipt_id=_receipt_id(event_type.value, command.idempotency_key.value), idempotency_key=f"{command.idempotency_key.value}:{event_type.value}", correlation_id=command.correlation_id.value)
                repo.save_receipt(command.idempotency_key.value, fingerprint, receipt)
                uow.commit()
                return receipt
            except HumanEscalationError:
                raise
            except Exception as error:
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True) from error

    def hold_guard(self, hold_scope: str, unit_of_work: object | None = None) -> AutomationHoldDecision:
        if unit_of_work is not None:
            return self._hold_guard(hold_scope, unit_of_work)
        with self._unit_of_work_factory() as uow:
            return self._hold_guard(hold_scope, uow)

    @staticmethod
    def _hold_guard(hold_scope: str, uow: object) -> AutomationHoldDecision:
        repo = _repo(uow)
        decision = getattr(repo, "active_hold", None)
        if decision is None:
            raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
        result = decision(hold_scope)
        if result is None:
            return AutomationHoldDecision(AutomationHoldState.RELEASED, hold_scope)
        if result.state is AutomationHoldState.ACTIVE:
            raise _error("domain_blocked", "automation_hold_active")
        return result

    def query(self, escalation_id: int) -> HumanEscalationView:
        with self._unit_of_work_factory() as uow:
            return _view(_load(_repo(uow), escalation_id))

    def _transition(self, command, event_type, expected_state, result_state) -> HumanEscalationReceipt:
        with self._unit_of_work_factory() as uow:
            repo = _repo(uow)
            fingerprint = _command_fingerprint(command)
            replay = _replay_receipt(repo, command.idempotency_key.value, fingerprint)
            if replay is not None:
                return replay
            _verify_preview(uow, command)
            escalation = _load(repo, command.escalation_id)
            _check_version(escalation, command.expected_escalation_version)
            _check_state(escalation, expected_state)
            try:
                updated = repo.transition(int(_field(escalation, "id")), workflow_status=result_state.value, workflow_version=command.expected_escalation_version + 1)
                receipt = self._receipt(updated, "claim", command.correlation_id.value, replayed=False)
                repo.append_event(int(_field(escalation, "id")), event_type, expected_escalation_version=command.expected_escalation_version, resulting_escalation_version=command.expected_escalation_version + 1, expected_hold_version=int(_field(escalation, "hold_version", 0)), resulting_hold_version=int(_field(escalation, "hold_version", 0)), actor_ref=command.actor.actor_id, reason_code=event_type.value, reason_evidence_digest=_digest(command), receipt_id=_receipt_id(event_type.value, command.idempotency_key.value), idempotency_key=command.idempotency_key.value, correlation_id=command.correlation_id.value)
                repo.save_receipt(command.idempotency_key.value, fingerprint, receipt)
                uow.commit()
                return receipt
            except Exception as error:
                if isinstance(error, HumanEscalationError):
                    raise
                raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True) from error

    def _receipt(self, row, operation: str, correlation_id: str, *, replayed: bool) -> HumanEscalationReceipt:
        status = EscalationWorkflowStatus(str(_field(row, "workflow_status", "open")))
        hold = AutomationHoldState(str(_field(row, "hold_state", _field(row, "automation_hold_state", "active"))))
        return HumanEscalationReceipt(_receipt_id(operation, str(_field(row, "id"))), _FAMILY, operation, int(_field(row, "id")), f"ticket:{int(_field(row, 'ticket_id'))}", status, hold, _version(row), replayed, correlation_id, _utc(self._now()))

    def _replay_or_conflict(self, repo, row, fingerprint: str, correlation_id: str, operation: str) -> HumanEscalationReceipt:
        stored = _field(row, "request_fingerprint", None)
        if stored is not None and str(stored) != fingerprint:
            raise _error("idempotency_mismatch", "human_escalation_idempotency_mismatch")
        saved = _field(row, "receipt", None)
        if isinstance(saved, HumanEscalationReceipt):
            return replace(saved, replayed=True)
        return self._receipt(row, operation, correlation_id, replayed=True)


def _preview_snapshot(uow, command, *, lock: bool) -> dict:
    repo = _repo(uow)
    if isinstance(command, CreateHumanEscalation):
        command_fingerprint = _command_fingerprint(command)
        target = _call(repo, "get_by_idempotency", command.idempotency_key.value, lock=lock)
        if target is not None:
            stored = _field(target, "request_fingerprint", None)
            if stored is not None and str(stored) != command_fingerprint:
                raise _error("idempotency_mismatch", "human_escalation_idempotency_mismatch")
        if target is None:
            target = _call(repo, "get_by_source", command.source_event_identity, lock=lock)
            if target is not None and _field(target, "source_fingerprint") != command.source_fingerprint:
                raise _error("conflict", "human_escalation_source_conflict")
        if target is None:
            target = _call(repo, "get_active_by_scope", command.hold_scope, lock=lock)
        if target is None:
            return _preview_values(
                "create", None, "absent", "open", "absent", "active", None, None
            )
        return _preview_values(
            "create",
            int(_field(target, "id")),
            str(_field(target, "workflow_status", "open")),
            str(_field(target, "workflow_status", "open")),
            str(_field(target, "hold_state", _field(target, "automation_hold_state", "active"))),
            str(_field(target, "hold_state", _field(target, "automation_hold_state", "active"))),
            int(_field(target, "workflow_version", 0)),
            _optional_int(_field(target, "ticket_version", None)),
        )

    escalation = _load(repo, command.escalation_id, lock=lock)
    _check_version(escalation, command.expected_escalation_version)
    before_status = EscalationWorkflowStatus(str(_field(escalation, "workflow_status", "open")))
    before_hold = AutomationHoldState(str(_field(escalation, "hold_state", _field(escalation, "automation_hold_state", "active"))))
    ticket_version = None
    if isinstance(command, ClaimHumanEscalation):
        _check_state(escalation, EscalationWorkflowStatus.OPEN)
        resulting_status = EscalationWorkflowStatus.CLAIMED
        resulting_hold = before_hold
        operation = "claim"
    else:
        ticket = _ticket(uow, escalation, lock=lock)
        ticket_version = int(_field(ticket, "version"))
        if ticket_version != command.expected_ticket_version:
            raise _error("conflict", "human_escalation_version_conflict")
        if isinstance(command, StartHumanEscalationHandling):
            _check_state(escalation, EscalationWorkflowStatus.CLAIMED)
            transition_ticket(CustomerServiceStatus(str(_field(ticket, "status"))), CustomerServiceStatus.HANDLING)
            resulting_status = EscalationWorkflowStatus.HANDLING
            resulting_hold = before_hold
            operation = "handling_started"
        else:
            _check_state(escalation, EscalationWorkflowStatus.HANDLING)
            if CustomerServiceStatus(str(_field(ticket, "status"))) is not CustomerServiceStatus.HANDLING:
                raise _error("domain_blocked", "automation_hold_release_blocked")
            source = getattr(uow, "escalation_source", None)
            if not _release_predicate_satisfied(escalation, source):
                raise _error("domain_blocked", "automation_hold_release_blocked")
            resulting_status = EscalationWorkflowStatus.RESOLVED
            resulting_hold = AutomationHoldState.RELEASED
            operation = "resolve"
    return _preview_values(
        operation,
        int(_field(escalation, "id")),
        before_status.value,
        resulting_status.value,
        before_hold.value,
        resulting_hold.value,
        int(_field(escalation, "workflow_version", 0)),
        ticket_version,
    )


def _preview_values(
    operation,
    escalation_id,
    before_status,
    resulting_status,
    before_hold,
    resulting_hold,
    escalation_version,
    ticket_version,
):
    return {
        "operation": operation,
        "escalation_id": escalation_id,
        "before_workflow_status": before_status,
        "resulting_workflow_status": resulting_status,
        "before_hold_state": before_hold,
        "resulting_hold_state": resulting_hold,
        "current_escalation_version": escalation_version,
        "current_ticket_version": ticket_version,
    }


def _preview_fingerprint(command, snapshot: dict) -> PreviewFingerprint:
    return fingerprint_payload(
        {"command_fingerprint": _command_fingerprint(command), "candidate": snapshot}
    )


def _verify_preview(uow, command) -> None:
    expected = getattr(command, "preview_fingerprint", None)
    if expected is None:
        return
    current = _preview_fingerprint(command, _preview_snapshot(uow, command, lock=True))
    if current != expected:
        raise _error("conflict", "human_escalation_preview_conflict")


def _optional_int(value) -> int | None:
    return None if value is None else int(value)


def _repo(uow):
    repo = getattr(uow, "escalations", None)
    if repo is None:
        raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
    return repo


def _release_predicate_satisfied(escalation: object, source: object | None) -> bool:
    """Route release evidence without treating runtime health as every owner."""

    try:
        trigger = TriggerCode(str(getattr(_field(escalation, "trigger_code"), "value", _field(escalation, "trigger_code"))))
    except (TypeError, ValueError):
        return False
    if trigger in {
        TriggerCode.EXPLICIT_HUMAN_REQUEST,
        TriggerCode.EXPLICIT_WRONG_ANSWER,
        TriggerCode.COMPLAINT,
    }:
        # The caller already locked a HANDLING escalation and HANDLING ticket;
        # ResolveHumanEscalation requires a bounded evidence digest.  These are
        # the Customer Service-owned release facts for conversation triggers.
        return True
    predicate = getattr(source, "can_release", None)
    return callable(predicate) and predicate(escalation) is True


def _call(repo, method: str, value, *, lock: bool):
    fn = getattr(repo, method, None)
    if fn is None:
        raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
    try:
        return fn(value, lock=lock)
    except HumanEscalationError:
        raise
    except LookupError:
        raise _error("not_found", "human_escalation_not_found")
    except Exception as error:
        raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True) from error


def _load(repo, escalation_id: int, *, lock: bool = True):
    row = _call(repo, "get_by_id", escalation_id, lock=lock)
    if row is None:
        raise _error("not_found", "human_escalation_not_found")
    return row


def _ticket(uow, escalation, *, lock: bool):
    port = getattr(uow, "customer_service", None)
    if port is None or not hasattr(port, "get"):
        raise _error("unavailable", "human_escalation_persistence_unavailable", retryable=True)
    try:
        return port.get(int(_field(escalation, "ticket_id")), lock=lock)
    except LookupError as error:
        raise _error("not_found", "human_escalation_not_found") from error


def _check_version(row, expected: int) -> None:
    current = int(_field(row, "workflow_version", 0))
    if current != expected:
        raise _error("conflict", "human_escalation_version_conflict")


def _check_state(row, expected: EscalationWorkflowStatus) -> None:
    current = EscalationWorkflowStatus(str(_field(row, "workflow_status", "open")))
    if current is not expected:
        raise _error("domain_blocked", "human_escalation_transition_invalid")


def _intent(escalation, ticket, command: CreateHumanEscalation) -> MaskedAlertIntent:
    context = command.masked_context if isinstance(command.masked_context, MaskedContext) else MaskedContext.from_mapping(command.masked_context)
    return MaskedAlertIntent(f"escalation:{int(_field(escalation, 'id'))}", f"ticket:{int(_field(escalation, 'ticket_id'))}", command.trigger_code, context.category, context.summary_code, AutomationHoldState.ACTIVE, command.correlation_id.value, command.source_fingerprint)


def _command_fingerprint(command) -> str:
    context = command.masked_context.as_dict() if isinstance(command, CreateHumanEscalation) and isinstance(command.masked_context, MaskedContext) else (dict(command.masked_context) if isinstance(command, CreateHumanEscalation) else None)
    data = {
        field.name: getattr(command, field.name)
        for field in fields(command)
        if field.name not in {"actor", "preview_fingerprint"}
    }
    if context is not None:
        data["masked_context"] = context
    for key in ("idempotency_key", "correlation_id"):
        if key in data:
            data[key] = data[key].value
    if "trigger_code" in data:
        data["trigger_code"] = data["trigger_code"].value
    return fingerprint_payload(data).value


def _digest(command) -> str:
    return hashlib.sha256(_command_fingerprint(command).encode()).hexdigest()


def _replay_receipt(repo, key: str, fingerprint: str):
    row = _call(repo, "get_by_idempotency", key, lock=True)
    if row is None:
        return None
    stored = _field(row, "request_fingerprint", None)
    if stored is not None and str(stored) != fingerprint:
        raise _error("idempotency_mismatch", "human_escalation_idempotency_mismatch")
    return _receipt_from_row(row, replayed=True)


def _receipt_from_row(row, *, replayed: bool):
    saved = _field(row, "receipt", None)
    if isinstance(saved, HumanEscalationReceipt):
        return replace(saved, replayed=replayed)
    status = EscalationWorkflowStatus(str(_field(row, "workflow_status", "open")))
    hold = AutomationHoldState(str(_field(row, "hold_state", _field(row, "automation_hold_state", "active"))))
    return HumanEscalationReceipt(_receipt_id("replay", str(_field(row, "id"))), _FAMILY, "replay", int(_field(row, "id")), f"ticket:{int(_field(row, 'ticket_id'))}", status, hold, _version(row), replayed, str(_field(row, "correlation_id", "replay")), _utc(datetime.now(timezone.utc)))


def _version(row) -> str:
    return fingerprint_payload({"id": int(_field(row, "id")), "workflow_version": int(_field(row, "workflow_version", 0)), "hold_version": int(_field(row, "hold_version", 0)), "status": str(_field(row, "workflow_status", "open"))}).value


def _view(row) -> HumanEscalationView:
    context = _field(row, "masked_context", {})
    if isinstance(context, str):
        raise _error("unavailable", "human_escalation_redaction_failed")
    safe = MaskedContext.from_mapping(context)
    from domains.customer_service.ticket import CustomerServiceCategory
    trigger_identity, attempt_window, owner_selector = _retry_readback(row)
    return HumanEscalationView(int(_field(row, "id")), f"ticket:{int(_field(row, 'ticket_id'))}", CustomerServiceCategory(str(_field(row, "ticket_category"))), "high", TriggerCode(str(_field(row, "trigger_code"))), EscalationWorkflowStatus(str(_field(row, "workflow_status"))), int(_field(row, "workflow_version", 0)), AutomationHoldState(str(_field(row, "hold_state", _field(row, "automation_hold_state", "active")))), "opaque", safe.as_dict(), AlertStatus(str(_field(row, "alert_status", AlertStatus.PENDING))), _version(row), _utc(_field(row, "created_at")), _utc(_field(row, "updated_at")), _actions(_field(row, "workflow_status"), _field(row, "hold_state", _field(row, "automation_hold_state", "active"))), _field(row, "delivery_task_ref"), _field(row, "delivery_outcome_ref"), trigger_identity, attempt_window, owner_selector)


_BINDING_FAILURE_SOURCE = re.compile(r"^binding-failure:([0-9a-f]{64}):(0|[1-9][0-9]*)$")


def _retry_readback(row):
    """Project only the opaque retry identity and bounded owner metadata."""
    if str(_field(row, "trigger_code", "")) not in {
        TriggerCode.BINDING_FAILURE_THRESHOLD_2.value,
        str(TriggerCode.BINDING_FAILURE_THRESHOLD_2),
    }:
        return None, None, None
    source = str(_field(row, "source_event_identity", ""))
    match = _BINDING_FAILURE_SOURCE.fullmatch(source)
    if match is None:
        return None, None, None
    return (
        source,
        HumanEscalationAttemptWindow(2, 2, int(match.group(2))),
        "customer_service.ticket_owner",
    )


def _actions(status, hold):
    status = str(status)
    if status == "open":
        return ("claim",)
    if status == "claimed":
        return ("handling",)
    if status == "handling" and str(hold) == "active":
        return ("resolve",)
    return ()


def _field(row, name: str, default=None):
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _receipt_id(operation: str, identity: str) -> str:
    return "receipt:" + hashlib.sha256(f"{_FAMILY}:{operation}:{identity}".encode()).hexdigest()[:32]


def _utc(value: datetime | None) -> datetime:
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _error(category: str, code: str, *, retryable: bool = False) -> HumanEscalationError:
    return HumanEscalationError(category, code, "客服 escalation 操作未完成", retryable=retryable)


__all__ = ["HumanEscalationApplication"]
