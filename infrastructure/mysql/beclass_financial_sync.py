"""Cross-owner financial synchronization for a pre-service BeClass rate correction."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from domains.client_finance.obligation_planning import (
    build_client_finance_rate_correction_candidate,
)
from domains.scheduling.generation import (
    AssignmentIdentityResolution,
    build_generation_candidate,
)
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import (
    _select_assignments,
    _select_generation,
    load_contract_client_finance_facts,
    load_locked_facts,
    preflight_staff_ids,
    select_order,
    select_scheduling_aggregate,
)
from infrastructure.mysql.payroll_terms_writer import persist_payroll_terms_impact
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    PayrollImpactPersistenceCommand,
)
from subsystems.payroll.terms_impact import build_payroll_rate_correction_impact


class MySqlBeClassFinancialSync:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def apply(
        self,
        *,
        case_no,
        correction_event_id,
        actor,
        reason,
        idempotency_key,
        correlation_id,
    ) -> None:
        with self._connection.cursor() as cursor:
            order_row = select_order(cursor, case_no, lock=True)
            has_assignments, finance_present = _load_rate_correction_presence(cursor, case_no)
            facts = None
            if has_assignments:
                staff_ids = preflight_staff_ids(cursor, case_no)
                facts = load_locked_facts(cursor, case_no, staff_ids)
            elif not finance_present:
                # The committed effective birth count is the input for later
                # bootstrap/rate resolution. No financial root exists to adjust.
                return
            finance_facts = load_contract_client_finance_facts(
                cursor, order_row, lock=True
            )
            change_identity = f"beclass-rate-correction:{correction_event_id}"
            _persist_effective_client_rate(
                cursor,
                finance_facts,
                correction_event_id,
                actor,
                reason,
                _child_key(idempotency_key, "client-payment-terms"),
            )
            finance_candidate = build_client_finance_rate_correction_candidate(
                finance_facts, change_identity
            )
            persist_client_finance_terms_impact(
                cursor,
                ClientFinanceImpactPersistenceCommand(
                    candidate=finance_candidate,
                    idempotency_key=_child_key(idempotency_key, "client-finance"),
                    actor=actor,
                    reason=reason,
                    correlation_id=correlation_id,
                    source_event_family="beclass-correction",
                    source_event_id=correction_event_id,
                ),
            )
            if facts is None:
                return
            scheduling = build_generation_candidate(
                facts.scheduling,
                facts.order.terms,
                facts.planned_service_dates,
            )
            payroll_candidate = build_payroll_rate_correction_impact(
                facts.payroll,
                scheduling,
                facts.order.terms,
                change_identity,
            )
            payroll_candidate = replace(
                payroll_candidate,
                carried_rate_snapshots=(),
                special_pay_events=(),
            )
            resolution = AssignmentIdentityResolution(
                {
                    item.candidate_key: int(item.source_assignment_id)
                    for item in scheduling.assignments
                    if item.source_assignment_id is not None
                }
            )
            persist_payroll_terms_impact(
                cursor,
                PayrollImpactPersistenceCommand(
                    candidate=payroll_candidate,
                    assignment_resolution=resolution,
                    idempotency_key=_child_key(idempotency_key, "payroll"),
                    actor=actor,
                    reason=reason,
                    correlation_id=correlation_id,
                    source_event_id=correction_event_id,
                ),
            )


def _load_rate_correction_presence(cursor, case_no):
    # The Orders root is already locked. Discover the branch without taking
    # downstream locks ahead of the existing staff/occupancy lock sequence.
    aggregate = select_scheduling_aggregate(cursor, case_no, lock=False)
    generation = _select_generation(cursor, aggregate, False)
    assignments = _select_assignments(cursor, generation, False)
    present = {}
    for table in (
        "client_finance_accounts", "client_payment_terms", "payroll_case_accounts",
        "case_payroll_rate_policy_snapshots", "client_obligations", "client_obligation_events",
        "client_ledger_entries", "staff_obligations", "staff_obligation_events",
    ):
        cursor.execute(f"SELECT case_no FROM {table} WHERE case_no=%s LIMIT 1", (case_no,))
        present[table] = cursor.fetchone() is not None
    finance = present["client_finance_accounts"]
    payroll = present["payroll_case_accounts"]
    if finance != present["client_payment_terms"] or (not finance and any(
        present[table] for table in ("client_obligations", "client_obligation_events", "client_ledger_entries")
    )):
        raise ValueError("invalid_client_finance_facts")
    if payroll != present["case_payroll_rate_policy_snapshots"] or (not payroll and any(
        present[table] for table in ("staff_obligations", "staff_obligation_events")
    )):
        raise ValueError("invalid_payroll_facts")
    if assignments and not (finance and payroll):
        raise ValueError("beclass_rate_correction_assignment_facts_inconsistent")
    if not assignments and (present["staff_obligations"] or present["staff_obligation_events"]):
        raise ValueError("beclass_rate_correction_payroll_facts_inconsistent")
    return bool(assignments), finance


def _persist_effective_client_rate(
    cursor,
    finance_facts,
    correction_event_id,
    actor,
    reason,
    key,
):
    terms = finance_facts.payment_terms
    cursor.execute(
        "SELECT policy_version,client_hourly_rate_ntd FROM client_payment_terms "
        "WHERE case_no=%s FOR UPDATE",
        (finance_facts.case_no,),
    )
    current = cursor.fetchone()
    if current is None:
        raise ValueError("client_finance_bootstrap_required")
    if int(current["client_hourly_rate_ntd"]) == terms.client_hourly_rate.amount:
        return
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            finance_facts.case_no,
            str(current["policy_version"]),
            terms.client_hourly_rate.amount,
            terms.deposit_service_days,
            terms.deposit_due_date,
            terms.first_payment_due_date,
            terms.second_payment_due_date,
            finance_facts.account_version,
            f"beclass-correction:{correction_event_id}",
            key.value,
            actor.actor_id,
            reason,
        ),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "UPDATE client_payment_terms SET client_hourly_rate_ntd=%s,current_event_id=%s "
        "WHERE case_no=%s",
        (terms.client_hourly_rate.amount, event_id, finance_facts.case_no),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("client_payment_terms_not_found")


def _child_key(parent: IdempotencyKey, purpose: str) -> IdempotencyKey:
    return IdempotencyKey(
        "child:" + fingerprint_payload(
            {"parent": parent.value, "purpose": purpose}
        ).value
    )


__all__ = ["MySqlBeClassFinancialSync"]
