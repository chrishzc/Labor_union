"""MySQL writer for typed Payroll impact inside Orders Terms Apply."""

from __future__ import annotations

import json

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.terms_workflow import PayrollImpactPersistenceCommand
from subsystems.payroll.terms_impact import PayrollTermsActionKind


def persist_payroll_terms_impact(cursor, command) -> None:
    _insert_carried_rate_snapshots(cursor, command)
    for ordinal, action in enumerate(command.candidate.actions, start=1):
        if not _action_requires_event(action):
            continue
        event_id = _append_obligation_event(cursor, command, action, ordinal)
        _persist_projection(cursor, command, action, event_id)
    _advance_payroll_version(cursor, command)
    _append_outbox(cursor, command)


def _action_requires_event(action) -> bool:
    return (
        action.action is not PayrollTermsActionKind.KEEP_FROZEN
        and action.amount.amount != 0
    )


def _insert_carried_rate_snapshots(cursor, command):
    rows = tuple(_rate_row(command, item) for item in command.candidate.carried_rate_snapshots)
    cursor.executemany(
        "INSERT INTO assignment_payroll_rate_snapshots "
        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
        "source_identity_status) VALUES (%s,%s,%s,%s,%s)",
        rows,
    )


def _rate_row(command, rate):
    assignment_id = _resolved_assignment_id(
        command,
        rate.assignment_identity,
    )
    return (
        assignment_id,
        rate.policy_version,
        rate.policy_kind.value,
        rate.hourly_rate.amount,
        _rate_source_identity(command, rate),
    )


def _append_obligation_event(cursor, command, action, ordinal):
    cursor.execute(
        _EVENT_INSERT_SQL,
        _event_values(command, action, ordinal),
    )
    return int(cursor.lastrowid)


# Kept cohesive because these columns form one immutable obligation event.
def _event_values(command, action, ordinal):
    assignment_id = _event_assignment_id(command, action)
    before_amount, after_amount = _event_amounts(action)
    return (
        action.obligation_identity,
        assignment_id,
        command.candidate.case_no,
        action.staff_id,
        action.obligation_kind.value,
        action.direction.value,
        action.source_obligation_identity,
        _event_type(action),
        before_amount,
        after_amount,
        action.due_date,
        command.candidate.payroll.fingerprint.value,
        command.candidate.expected_payroll_version,
        command.candidate.resulting_payroll_version,
        _child_identity(command, "event", ordinal),
        command.actor.actor_id,
        command.reason,
    )


def _event_assignment_id(command, action):
    if action.candidate_assignment_key is not None:
        return _resolved_assignment_id(command, action.candidate_assignment_key)
    return action.source_assignment_id


def _event_amounts(action):
    if action.action is PayrollTermsActionKind.CLOSE_UNPAID:
        return action.amount.amount, 0
    return 0, action.amount.amount


def _event_type(action):
    if action.action is PayrollTermsActionKind.ESTABLISH:
        return "established"
    if action.action is PayrollTermsActionKind.CLOSE_UNPAID:
        return "rebuilt"
    if action.obligation_kind.value == "reversal":
        return "reversal"
    return "adjustment"


def _persist_projection(cursor, command, action, event_id):
    if action.action is PayrollTermsActionKind.CLOSE_UNPAID:
        _close_projection(cursor, command, action, event_id)
        return
    _insert_projection(cursor, command, action, event_id)


def _close_projection(cursor, command, action, event_id):
    cursor.execute(
        "UPDATE staff_obligations SET amount_due_ntd=0,status='cancelled',"
        "current_event_id=%s,payroll_version=%s "
        "WHERE obligation_identity=%s AND case_no=%s "
        "AND payout_history_exists=0",
        (
            event_id,
            command.candidate.resulting_payroll_version,
            action.obligation_identity,
            command.candidate.case_no,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("staff_obligation_frozen")


def _insert_projection(cursor, command, action, event_id):
    cursor.execute(
        _PROJECTION_INSERT_SQL,
        (
            action.obligation_identity,
            _event_assignment_id(command, action),
            command.candidate.case_no,
            action.staff_id,
            action.obligation_kind.value,
            action.direction.value,
            action.source_obligation_identity,
            action.amount.amount,
            action.due_date,
            "open",
            event_id,
            command.candidate.resulting_payroll_version,
            0,
        ),
    )


def _advance_payroll_version(cursor, command):
    cursor.execute(
        "UPDATE payroll_case_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            command.candidate.resulting_payroll_version,
            command.candidate.case_no,
            command.candidate.expected_payroll_version,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("payroll_candidate_stale")


def _append_outbox(cursor, command):
    payload = {
        "case_no": command.candidate.case_no,
        "impact_fingerprint": command.candidate.fingerprint.value,
        "payroll_version": command.candidate.resulting_payroll_version,
    }
    cursor.execute(
        "INSERT INTO payroll_outbox "
        "(case_no,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,'staff_obligation_changed',%s)",
        (
            command.candidate.case_no,
            _child_identity(command, "outbox", 1),
            _canonical_json(payload),
        ),
    )


def _resolved_assignment_id(command, candidate_key):
    if candidate_key is None:
        raise ValueError("candidate assignment key is required")
    assignment_id = command.assignment_resolution.assignment_id_by_candidate_key.get(
        candidate_key
    )
    if assignment_id is None:
        raise ValueError("assignment identity resolution is incomplete")
    return assignment_id


def _source_assignment_id(command, candidate_key):
    return next(
        action.source_assignment_id
        for action in command.candidate.actions
        if action.candidate_assignment_key == candidate_key
    )


def _rate_source_identity(command, rate):
    source_assignment_id = _source_assignment_id(
        command, rate.assignment_identity
    )
    if source_assignment_id is not None:
        return f"carried-from:{source_assignment_id}"
    return "case-policy"


def _child_identity(command, purpose, ordinal):
    return "child:" + fingerprint_payload(
        {
            "outer_key": command.idempotency_key.value,
            "domain": "payroll",
            "purpose": purpose,
            "ordinal": ordinal,
        }
    ).value


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_EVENT_INSERT_SQL = (
    "INSERT INTO staff_obligation_events "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,event_type,before_amount_ntd,"
    "after_amount_ntd,due_date,payroll_fingerprint,"
    "expected_payroll_version,resulting_payroll_version,idempotency_key,"
    "actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
    "%s,%s,%s,%s)"
)

_PROJECTION_INSERT_SQL = (
    "INSERT INTO staff_obligations "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,payroll_version,payout_history_exists) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
