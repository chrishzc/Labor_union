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
    _persist_payment_terms(cursor, command)
    for ordinal, action in enumerate(command.candidate.actions, start=1):
        if action.action is ClientObligationActionKind.UNCHANGED:
            continue
        event_id = _append_obligation_event(cursor, command, action, ordinal)
        _persist_projection(cursor, command, action, event_id)
    changed = False
    if getattr(command.candidate, "subsidy_return_plan", None) is not None:
        changed = persist_subsidy_return_plan(cursor, command)
    if (
        not command.candidate.actions
        and command.candidate.payment_terms is None
        and not changed
        and command.candidate.resulting_account_version == command.candidate.expected_account_version
    ):
        return
    _advance_account_version(cursor, command)
    _append_outbox(cursor, command)


def _persist_payment_terms(cursor, command):
    second = next((stage for stage in command.candidate.stage_plans
                   if stage.payment_stage is PaymentStage.SECOND), None)
    terms = command.candidate.payment_terms
    if second is None and terms is None:
        return
    cursor.execute(
        "SELECT policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id "
        "FROM client_payment_terms WHERE case_no=%s FOR UPDATE",
        (command.candidate.case_no,),
    )
    current = cursor.fetchone()
    if current is None:
        raise ValueError("client_finance_bootstrap_required")
    values = {
        "client_hourly_rate_ntd": terms.client_hourly_rate.amount if terms is not None else current["client_hourly_rate_ntd"],
        "deposit_service_days": terms.deposit_service_days if terms is not None else current["deposit_service_days"],
        "deposit_due_date": terms.deposit_due_date if terms is not None else current["deposit_due_date"],
        "first_payment_due_date": terms.first_payment_due_date if terms is not None else current["first_payment_due_date"],
        "second_payment_due_date": terms.second_payment_due_date if terms is not None else second.due_date,
    }
    if all(current[name] == value for name, value in values.items()):
        return
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (command.candidate.case_no, current["policy_version"],
         values["client_hourly_rate_ntd"], values["deposit_service_days"],
         values["deposit_due_date"], values["first_payment_due_date"], values["second_payment_due_date"],
         command.candidate.expected_account_version,
         f"{command.source_event_family}:{command.source_event_id}:payment-terms",
         _child_identity(command, "payment_terms", 1), command.actor.actor_id, command.reason),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "UPDATE client_payment_terms SET second_payment_due_date=%s,first_payment_due_date=%s,"
        "deposit_due_date=%s,client_hourly_rate_ntd=%s,deposit_service_days=%s,current_event_id=%s "
        "WHERE case_no=%s AND current_event_id=%s",
        (values["second_payment_due_date"], values["first_payment_due_date"], values["deposit_due_date"],
         values["client_hourly_rate_ntd"], values["deposit_service_days"], event_id,
         command.candidate.case_no, current["current_event_id"]),
    )
    if cursor.rowcount != 1:
        raise ValueError("client_finance_payment_terms_conflict")


def _append_obligation_event(cursor, command, action, ordinal):
    cursor.execute(_EVENT_INSERT_SQL, _event_values(command, action, ordinal))
    return int(cursor.lastrowid)


def persist_subsidy_return_plan(cursor, command):
    plan = command.candidate.subsidy_return_plan
    cursor.execute('SELECT o.obligation_identity,o.amount_due_ntd,o.due_date,e.after_amount_ntd '
        'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
        "WHERE o.case_no=%s AND o.obligation_type='subsidy_return' ORDER BY o.obligation_identity FOR UPDATE",
        (command.candidate.case_no,))
    existing = tuple(cursor.fetchall())
    if len(existing) > 1:
        raise ValueError('subsidy_return_lineage_ambiguous')
    current = existing[0] if existing else None
    identity = current['obligation_identity'] if current else plan.obligation_identity
    cursor.execute('SELECT COALESCE(SUM(CASE WHEN ledger.entry_type IN (\'subsidy_return\',\'subsidy_advance\') '
        'THEN allocation.amount_ntd WHEN ledger.entry_type IN (\'reversal\',\'subsidy_return_reversal\') THEN -allocation.amount_ntd ELSE 0 END),0) paid '
        'FROM client_ledger_obligation_allocations allocation JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id '
        'WHERE allocation.obligation_identity=%s', (identity,))
    paid = int(cursor.fetchone()['paid'])
    cursor.execute('SELECT COALESCE(SUM(CASE WHEN ledger.entry_type=\'receipt\' THEN allocation.amount_ntd '
        'WHEN ledger.entry_type=\'reversal\' THEN -allocation.amount_ntd ELSE 0 END),0) recovered '
        'FROM client_ledger_obligation_allocations allocation JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id '
        'WHERE allocation.obligation_identity=%s',(identity+':difference',))
    recovered=int(cursor.fetchone()['recovered'])
    remaining = max(0, plan.amount.amount - paid + recovered)
    if current and int(current['after_amount_ntd']) == plan.amount.amount and current['due_date'] == plan.due_date:
        return False
    ordinal = len(command.candidate.actions) + 1
    cursor.execute(
        _EVENT_INSERT_SQL,
        (
            identity,
            command.candidate.case_no,
            "subsidy_return",
            "payable_to_client",
            "recalculated" if current else "established",
            int(current['after_amount_ntd']) if current else 0,
            plan.amount.amount,
            current['due_date'] if current else None,
            plan.due_date,
            _source_event_identity(command, ordinal),
            None,
            command.candidate.expected_account_version,
            _child_identity(command, "event", ordinal),
            command.actor.actor_id,
            command.reason,
        ),
    )
    event_id = int(cursor.lastrowid)
    if current:
        cursor.execute(_PROJECTION_UPDATE_SQL, (remaining,plan.due_date,'open' if remaining else 'cancelled' if plan.amount.amount==0 and paid==0 else 'settled',
            event_id,command.candidate.resulting_account_version,identity,command.candidate.case_no))
        # Preserve actual cash; an over-refund is a receivable difference, never a rewritten payment.
        _persist_subsidy_overrefund(cursor,command,identity,max(0,paid-plan.amount.amount),plan.due_date,ordinal+1)
        return True
    cursor.execute(
        _PROJECTION_INSERT_SQL,
        (
            plan.obligation_identity,
            command.candidate.case_no,
            "subsidy_return",
            "payable_to_client",
            None,
            remaining,
            plan.due_date,
            "open",
            event_id,
            command.candidate.resulting_account_version,
        ),
    )
    return True


def _persist_subsidy_overrefund(cursor,command,source,amount,due,ordinal):
    identity = source + ':difference'
    cursor.execute('SELECT o.amount_due_ntd,e.after_amount_ntd FROM client_obligations o '
                   'JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.obligation_identity=%s FOR UPDATE', (identity,))
    current = cursor.fetchone()
    if not current and not amount:
        return
    already_paid = int(current['after_amount_ntd']) - int(current['amount_due_ntd']) if current else 0
    amount=max(amount,already_paid)
    if current and int(current['after_amount_ntd']) == amount:
        return
    cursor.execute(_EVENT_INSERT_SQL,(identity,command.candidate.case_no,'adjustment','receivable_from_client',
        'recalculated' if current else 'established',int(current['after_amount_ntd']) if current else 0,amount,
        due if current else None,due,_source_event_identity(command,ordinal),source,
        command.candidate.expected_account_version,_child_identity(command,'event',ordinal),command.actor.actor_id,command.reason))
    event_id = int(cursor.lastrowid)
    if current:
        remaining = max(0,amount-already_paid)
        cursor.execute(_PROJECTION_UPDATE_SQL,(remaining,due,'open' if remaining else 'settled',event_id,
            command.candidate.resulting_account_version,identity,command.candidate.case_no))
    else:
        cursor.execute(_PROJECTION_INSERT_SQL,(identity,command.candidate.case_no,'adjustment','receivable_from_client',
            source,amount,due,'open',event_id,command.candidate.resulting_account_version))


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
