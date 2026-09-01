"""LINE Identity consumer for an Orders terminal-closure handoff."""

from __future__ import annotations

from typing import Callable, Iterable, Mapping

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from shared_kernel.identities import IdempotencyReceipt
from subsystems.line.rich_menu_binding import schedule_staff_default_restore_menu
from subsystems.line.terminal_closure_contracts import (
    TerminalClosureDecision,
    TerminalClosureReadback,
    TerminalClosureSourceEvent,
)

_TERMINAL_STATUSES = {"訂單完成", "訂單取消"}


class TerminalClosureConsumerError(RuntimeError):
    """Closed, typed failure; callers must reconcile instead of blind retry."""


def consume_terminal_closure(
    unit_of_work_factory: Callable[[], object],
    event: TerminalClosureSourceEvent,
) -> TerminalClosureReadback:
    """Fresh-read LINE roots, then append one menu intent and receipt at most once."""

    if event.source_subject is None or event.source_subject == "":
        raise TerminalClosureConsumerError("line_terminal_closure_subject_missing")
    if event.source_subject != event.source_subject.strip():
        raise TerminalClosureConsumerError("line_terminal_closure_subject_invalid")
    line_user_id = _line_user(event)
    with unit_of_work_factory() as unit_of_work:
        existing = unit_of_work.receipts.get(event.idempotency_key)
        if existing is not None:
            if existing.payload_fingerprint != event.payload_fingerprint:
                raise TerminalClosureConsumerError("line_terminal_closure_idempotency_conflict")
            original = _decision_from_receipt(existing.result_reference)
            return TerminalClosureReadback(
                event.source_event_identity,
                event.case_no,
                event.orders_version,
                event.binding_version,
                TerminalClosureDecision.NOOP_REPLAY,
                receipt_identity=existing.result_reference,
                replay_of=original,
            )

        case = unit_of_work.identity_management.terminal_closure_case(event.case_no)
        _validate_case(event, case)
        bindings = tuple(unit_of_work.identities.list_by_user(line_user_id))
        staff = _staff_binding(bindings)
        if staff is None:
            raise TerminalClosureConsumerError("line_terminal_closure_staff_binding_missing")
        if staff.status in {
            LineIdentityBindingStatus.REVOCATION_PENDING,
            LineIdentityBindingStatus.REVOKED,
        }:
            return _record_decision(
                unit_of_work,
                event,
                staff.version.value,
                TerminalClosureDecision.BLOCKED_REVOKED_STAFF,
            )
        if staff.status is not LineIdentityBindingStatus.BOUND:
            raise TerminalClosureConsumerError("line_terminal_closure_staff_binding_inactive")
        if event.binding_version is not None and event.binding_version != staff.version.value:
            raise TerminalClosureConsumerError("line_terminal_closure_binding_stale")
        _validate_capability_and_menu(unit_of_work, event)
        active_cases = tuple(
            unit_of_work.identity_management.active_client_cases(line_user_id)
        )
        if any(not _case_terminal(item) for item in active_cases):
            return _record_decision(
                unit_of_work,
                event,
                staff.version.value,
                TerminalClosureDecision.BLOCKED_ACTIVE_CLIENT_CASE,
            )
        menu_intent = schedule_staff_default_restore_menu(
            unit_of_work,
            staff,
            event.source_event_identity,
            event.menu_revision,
        )
        receipt_identity = f"line-terminal-closure:{event.source_event_identity}:restored"
        unit_of_work.receipts.append(
            IdempotencyReceipt(event.idempotency_key, event.payload_fingerprint, receipt_identity)
        )
        unit_of_work.commit()
        return TerminalClosureReadback(
            event.source_event_identity,
            event.case_no,
            event.orders_version,
            staff.version.value,
            TerminalClosureDecision.RESTORED,
            menu_intent_identity=menu_intent,
            receipt_identity=receipt_identity,
        )


def _line_user(event: TerminalClosureSourceEvent):
    from domains.line.identities import LineUserId

    return LineUserId(event.source_subject)


def _staff_binding(bindings: Iterable[object]):
    candidates = tuple(
        binding
        for binding in bindings
        if binding.subject_type is LineBindingSubjectType.STAFF
    )
    if len(candidates) != 1:
        raise TerminalClosureConsumerError("line_terminal_closure_staff_binding_ambiguous")
    return candidates[0]


def _validate_case(event, case: Mapping[str, object] | None) -> None:
    if not case:
        raise TerminalClosureConsumerError("line_terminal_closure_case_missing")
    if str(case.get("case_no")) != event.case_no:
        raise TerminalClosureConsumerError("line_terminal_closure_case_mismatch")
    if int(case.get("lifecycle_version", -1)) != event.orders_version:
        raise TerminalClosureConsumerError("line_terminal_closure_orders_stale")
    if str(case.get("status")) not in _TERMINAL_STATUSES:
        raise TerminalClosureConsumerError("line_terminal_closure_case_not_terminal")
    owner = case.get("line_user_id")
    if owner is not None and owner != event.source_subject:
        raise TerminalClosureConsumerError("line_terminal_closure_subject_mismatch")


def _validate_capability_and_menu(unit_of_work, event) -> None:
    if event.capability != "staff_default_restore":
        raise TerminalClosureConsumerError("line_terminal_closure_capability_mismatch")
    publication = unit_of_work.identity_management.staff_menu_publication()
    if not publication:
        raise TerminalClosureConsumerError("line_terminal_closure_menu_unavailable")
    if event.menu_revision is not None and int(publication["id"]) != event.menu_revision:
        raise TerminalClosureConsumerError("line_terminal_closure_menu_stale")


def _case_terminal(case: Mapping[str, object]) -> bool:
    return str(case.get("status")) in _TERMINAL_STATUSES and bool(
        case.get("owner_readback_verified", True)
    )


def _record_decision(unit_of_work, event, binding_version, decision):
    receipt_identity = f"line-terminal-closure:{event.source_event_identity}:{decision.value}"
    unit_of_work.receipts.append(
        IdempotencyReceipt(event.idempotency_key, event.payload_fingerprint, receipt_identity)
    )
    unit_of_work.commit()
    return TerminalClosureReadback(
        event.source_event_identity,
        event.case_no,
        event.orders_version,
        binding_version,
        decision,
        receipt_identity=receipt_identity,
    )


def _decision_from_receipt(reference: str) -> TerminalClosureDecision:
    try:
        value = reference.rsplit(":", 1)[1]
        return TerminalClosureDecision(value)
    except (IndexError, ValueError) as error:
        raise TerminalClosureConsumerError("line_terminal_closure_receipt_invalid") from error


__all__ = ["TerminalClosureConsumerError", "consume_terminal_closure"]
