"""MySQL writer for typed Client Finance impact inside Orders Terms Apply."""

from __future__ import annotations

import json

from domains.client_finance.obligation_planning import (
    ClientObligationAction,
    ClientObligationActionKind,
)
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
)


def persist_client_finance_terms_impact(cursor, command) -> None:
    for ordinal, action in enumerate(command.candidate.actions, start=1):
        if action.action is ClientObligationActionKind.UNCHANGED:
            continue
        event_id = _append_obligation_event(cursor, command, action, ordinal)
        _persist_projection(cursor, command, action, event_id)
    _advance_account_version(cursor, command)
    _append_outbox(cursor, command)


def _append_obligation_event(cursor, command, action, ordinal):
    cursor.execute(_EVENT_INSERT_SQL, _event_values(command, action, ordinal))
    return int(cursor.lastrowid)


def _event_values(command, action, ordinal):
    before_amount, after_amount = _event_amounts(action)
    return (
        action.obligation_identity,
        command.candidate.case_no,
        _obligation_type(action),
        _direction(action),
        _event_type(action),
        before_amount,
        after_amount,
        action.before_due_date,
        action.after_due_date,
        _source_event_identity(command, ordinal),
        action.source_obligation_identity,
        command.candidate.expected_account_version,
        _child_identity(command, "event", ordinal),
        command.actor.actor_id,
        command.reason,
    )


def _event_amounts(action):
    if action.action in {
        ClientObligationActionKind.CREATE_ADJUSTMENT,
        ClientObligationActionKind.CREATE_REFUND,
    }:
        return 0, action.obligation_amount.amount
    return action.before_amount.amount, action.after_amount.amount


def _source_event_identity(command, ordinal):
    return (
        f"{command.source_event_family}:{command.source_event_id}:"
        f"client-finance:{ordinal}"
    )


def _obligation_type(action):
    if action.action is ClientObligationActionKind.CREATE_ADJUSTMENT:
        return "adjustment"
    if action.action is ClientObligationActionKind.CREATE_REFUND:
        return "refund"
    return action.payment_stage.value


def _direction(action):
    if action.action is ClientObligationActionKind.CREATE_REFUND:
        return "payable_to_client"
    return "receivable_from_client"


def _event_type(action):
    if action.action is ClientObligationActionKind.CREATE_STAGE:
        return "established"
    if action.action in {
        ClientObligationActionKind.REPLACE_OPEN,
        ClientObligationActionKind.CANCEL_OPEN,
    }:
        return "recalculated"
    return "adjusted"


def _persist_projection(cursor, command, action, event_id):
    if action.action in {
        ClientObligationActionKind.CREATE_STAGE,
        ClientObligationActionKind.CREATE_ADJUSTMENT,
        ClientObligationActionKind.CREATE_REFUND,
    }:
        _insert_projection(cursor, command, action, event_id)
        return
    _update_projection(cursor, command, action, event_id)


def _insert_projection(cursor, command, action, event_id):
    cursor.execute(
        _PROJECTION_INSERT_SQL,
        (
            action.obligation_identity,
            command.candidate.case_no,
            _obligation_type(action),
            _direction(action),
            action.source_obligation_identity,
            action.obligation_amount.amount,
            action.after_due_date,
            "open",
            event_id,
            command.candidate.resulting_account_version,
        ),
    )


def _update_projection(cursor, command, action, event_id):
    status = "cancelled" if action.after_amount.is_zero else "open"
    cursor.execute(
        _PROJECTION_UPDATE_SQL,
        (
            action.after_amount.amount,
            action.after_due_date,
            status,
            event_id,
            command.candidate.resulting_account_version,
            action.obligation_identity,
            command.candidate.case_no,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("client_obligation_not_found")


def _advance_account_version(cursor, command):
    cursor.execute(
        "UPDATE client_finance_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            command.candidate.resulting_account_version,
            command.candidate.case_no,
            command.candidate.expected_account_version,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("client_finance_candidate_stale")


def _append_outbox(cursor, command):
    payload = {
        "account_version": command.candidate.resulting_account_version,
        "case_no": command.candidate.case_no,
        "impact_fingerprint": command.candidate.fingerprint.value,
    }
    cursor.execute(
        "INSERT INTO client_finance_outbox "
        "(case_no,intent_type,intent_key,payload_snapshot) "
        "VALUES (%s,'projection_refresh',%s,%s)",
        (
            command.candidate.case_no,
            _child_identity(command, "outbox", 1),
            _canonical_json(payload),
        ),
    )


def _child_identity(command, purpose, ordinal):
    return "child:" + fingerprint_payload(
        {
            "outer_key": command.idempotency_key.value,
            "domain": "client_finance",
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
    "INSERT INTO client_obligation_events "
    "(obligation_identity,case_no,obligation_type,direction,event_type,"
    "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
    "source_event_identity,source_obligation_identity,"
    "expected_account_version,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_PROJECTION_INSERT_SQL = (
    "INSERT INTO client_obligations "
    "(obligation_identity,case_no,obligation_type,direction,"
    "source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,projection_version) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_PROJECTION_UPDATE_SQL = (
    "UPDATE client_obligations SET amount_due_ntd=%s,due_date=%s,status=%s,"
    "current_event_id=%s,projection_version=%s "
    "WHERE obligation_identity=%s AND case_no=%s"
)
