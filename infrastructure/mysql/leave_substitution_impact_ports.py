"""MySQL cross-Domain ports for leave/substitution Apply."""

from __future__ import annotations

from typing import Any
from dataclasses import replace
from shared_kernel.fingerprints import fingerprint_payload

from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_lifecycle_impact_writer import (
    persist_order_lifecycle_impact,
    persist_order_lifecycle_projection,
)
from infrastructure.mysql.payroll_terms_writer import (
    persist_payroll_terms_impact,
)
from shared_kernel.clock import BusinessClock
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    LifecycleImpactPersistenceCommand,
    PayrollImpactPersistenceCommand,
)
from subsystems.scheduling.assignment_plan_impacts import (
    AssignmentPlanDomainImpact,
    OrdersAssignmentImpactPayload,
    build_client_finance_assignment_impact,
    build_orders_assignment_impact,
    build_payroll_assignment_impact,
)


class MySqlClientFinanceLeaveImpactPort:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview_leave_substitution(self, facts, scheduling):
        dates = tuple(day for assignment in scheduling.assignments for day in assignment.service_dates)
        facts = replace(facts, client_finance=replace(facts.client_finance,effective_start_date=min(dates)))
        return build_client_finance_assignment_impact(facts, scheduling)

    def persist_leave_substitution(self, candidate, context, scheduling_result):
        impact = _domain_impact(candidate)
        command = ClientFinanceImpactPersistenceCommand(
            candidate=impact.payload,
            idempotency_key=context.idempotency_key,
            actor=context.actor,
            reason=context.reason,
            correlation_id=context.correlation_id,
            source_event_family="leave-substitution",
            source_event_id=scheduling_result.rebuild_event_id,
        )
        with self._connection.cursor() as cursor:
            persist_client_finance_terms_impact(cursor, command)


class MySqlPayrollLeaveImpactPort:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview_leave_substitution(self, facts, scheduling):
        client_finance = MySqlClientFinanceLeaveImpactPort(self._connection).preview_leave_substitution(facts, scheduling)
        return build_payroll_assignment_impact(facts, scheduling, client_finance)

    def preview_handover(self, facts, scheduling):
        client_finance = build_client_finance_assignment_impact(facts, scheduling)
        return build_payroll_assignment_impact(facts, scheduling, client_finance, handover=True)

    def persist_leave_substitution(self, candidate, context, scheduling_result):
        impact = _domain_impact(candidate)
        command = PayrollImpactPersistenceCommand(
            candidate=impact.payload,
            assignment_resolution=scheduling_result.assignment_resolution,
            idempotency_key=context.idempotency_key,
            actor=context.actor,
            reason=context.reason,
            correlation_id=context.correlation_id,
            source_event_id=scheduling_result.rebuild_event_id,
            special_pay_events=impact.payload.special_pay_events,
        )
        with self._connection.cursor() as cursor:
            persist_payroll_terms_impact(cursor, command)


class MySqlOrdersLeaveImpactPort:
    def __init__(self, connection: Any, clock: BusinessClock) -> None:
        self._connection = connection
        self._clock = clock

    def preview_leave_substitution(self, facts, scheduling, client_finance):
        start = min(day for assignment in scheduling.assignments for day in assignment.service_dates)
        impact = build_orders_assignment_impact(
            replace(facts, lifecycle=replace(facts.lifecycle,actual_start_date=start)),
            scheduling,
            client_finance,
            self._clock.now(),
        )
        return replace(impact, payload=replace(impact.payload,actual_start_date=start),
            fingerprint=fingerprint_payload({'impact':impact.fingerprint.value,'actual_start_date':str(start)}))

    def persist_leave_substitution(self, candidate, context, scheduling_result):
        del scheduling_result
        impact = _domain_impact(candidate)
        payload = _orders_payload(impact)
        command = LifecycleImpactPersistenceCommand(
            candidate=payload.lifecycle,
            expected_order_version=impact.expected_version,
            resulting_order_version=impact.resulting_version,
            client_settlement_fingerprint=payload.client_settlement_fingerprint,
            idempotency_key=context.idempotency_key,
            actor=context.actor,
            reason=context.reason,
            correlation_id=context.correlation_id,
            trigger_event="leave_substitution_applied",
            staff_payment_due_date=payload.staff_payment_due_date,
            actual_start_date=payload.actual_start_date,
        )
        with self._connection.cursor() as cursor:
            persist_order_lifecycle_impact(cursor, command)
            persist_order_lifecycle_projection(cursor, command)


def _domain_impact(candidate):
    if not isinstance(candidate, AssignmentPlanDomainImpact):
        raise TypeError("leave/substitution impact candidate is invalid")
    return candidate


def _orders_payload(impact):
    if not isinstance(impact.payload, OrdersAssignmentImpactPayload):
        raise TypeError("Orders leave/substitution impact payload is invalid")
    return impact.payload
