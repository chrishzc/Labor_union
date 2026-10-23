"""Approve one customer-authored condition round through the canonical Orders writer."""
from __future__ import annotations

import json
from typing import Protocol

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.replacement_matching_query import candidate_contact_open
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.orders.terms_workflow import OrderTermsApplyRequest


class AdjustmentTermsPort(Protocol):
    def preview(self, case_no, proposed_terms): ...
    def apply_in_current_uow(self, request): ...


class CandidateAdjustmentReviewApplication:
    def __init__(self, connection, terms: AdjustmentTermsPort):
        self._connection = connection
        self._terms = terms

    def approve(self, case_no, pool_id, answer_id, proposed_terms, expected_order_version, actor, event_key):
        with MySqlUnitOfWork(self._connection) as transaction:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT orders.lifecycle_version,orders.status FROM orders "
                    "JOIN caregiver_candidate_contact_pools pool ON pool.case_no=orders.case_no "
                    "WHERE pool.id=%s AND orders.case_no=%s FOR UPDATE", (pool_id, case_no),
                )
                order = cursor.fetchone()
                if not order or not candidate_contact_open(cursor, case_no, order['status']):
                    raise ValueError('candidate_adjustment_case_closed')
                cursor.execute(
                    "SELECT id,candidate_id,event_type,event_key,payload FROM caregiver_candidate_contact_events "
                    "WHERE pool_id=%s ORDER BY id FOR UPDATE", (pool_id,),
                )
                events = tuple(cursor.fetchall() or ())
                command = {
                    'customer_answer_event_id': answer_id, 'reviewed_terms': proposed_terms.canonical_payload(),
                    'expected_order_version': expected_order_version, 'actor': actor.actor_id,
                }
                existing = next((item for item in events if item['event_key'] == event_key.value), None)
                if existing:
                    stored = _payload(existing)
                    if stored.get('response_kind') != 'adjustment_approved' or stored.get('command') != command:
                        raise ValueError('candidate_adjustment_idempotency_conflict')
                    transaction.commit()
                    return {'status': 'idempotent_replay', 'approval_event_id': int(existing['id']), 'order_version': int(stored['order_version'])}
                answer = next((item for item in events if int(item['id']) == answer_id), None)
                if not answer or _payload(answer).get('response_kind') != 'adjustment_customer_answer':
                    raise ValueError('candidate_adjustment_answer_not_found')
                request_id = int(_payload(answer)['source_coordination_event_id'])
                question_id = int(_payload(answer)['source_response_event_id'])
                rounds = [item for item in events if _payload(item).get('response_kind') == 'adjustment_question_sent'
                          and int(_payload(item).get('source_response_event_id') or 0) == question_id]
                candidate_responses = [item for item in events if item.get('candidate_id') == answer.get('candidate_id')
                    and (_payload(item).get('willingness') in {'pending', 'willing', 'unwilling'}
                         or _payload(item).get('response_kind') in {'coordination_requested', 'no_interest'})]
                if (not rounds or int(rounds[-1]['id']) != request_id or not candidate_responses
                    or int(candidate_responses[-1]['id']) != question_id):
                    raise ValueError('candidate_adjustment_round_stale')
                if any(_payload(item).get('response_kind') == 'adjustment_approved'
                       and _payload(item).get('customer_answer_event_id') == answer_id for item in events):
                    raise ValueError('candidate_adjustment_already_approved')
                if int(order['lifecycle_version']) != expected_order_version:
                    raise ValueError('candidate_adjustment_order_conflict')
                preview = self._terms.preview(case_no, proposed_terms)
                if preview.order_version != expected_order_version:
                    raise ValueError('candidate_adjustment_order_conflict')
                if preview.before == preview.after:
                    raise ValueError('candidate_adjustment_new_conditions_unchanged')
                request = OrderTermsApplyRequest(
                    case_no, proposed_terms, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
                    ExpectedVersion(preview.client_finance_version) if preview.client_finance_version is not None else None,
                    ExpectedVersion(preview.payroll_version) if preview.payroll_version is not None else None,
                    preview.fingerprint, event_key, actor, '工會審核客戶更新後條件通過',
                    CorrelationId(f'candidate-adjustment:{pool_id}:{answer_id}'),
                    requires_formal_apply=preview.requires_formal_apply,
                )
                receipt = self._terms.apply_in_current_uow(request)
                payload = {'response_kind': 'adjustment_approved', 'command': command,
                           'customer_answer_event_id': answer_id, 'order_version': receipt.order_version}
                cursor.execute(
                    "INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) "
                    "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                    (pool_id, answer['candidate_id'], event_key.value, actor.actor_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
                )
                result = {'status': 'approved', 'approval_event_id': int(cursor.lastrowid), 'order_version': receipt.order_version}
            transaction.commit()
            return result


def _payload(row):
    value = row.get('payload')
    return json.loads(value) if isinstance(value, str) else value or {}
