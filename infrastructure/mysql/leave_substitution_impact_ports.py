"""MySQL cross-Domain ports for leave/substitution Apply."""

from __future__ import annotations

from typing import Any

from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_lifecycle_impact_writer import (
    persist_order_lifecycle_impact,
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
        return build_payroll_assignment_impact(facts, scheduling)

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
        )
        with self._connection.cursor() as cursor:
            persist_payroll_terms_impact(cursor, command)


class MySqlOrdersLeaveImpactPort:
    def __init__(self, connection: Any, clock: BusinessClock) -> None:
        self._connection = connection
        self._clock = clock

    def preview_leave_substitution(self, facts, scheduling, client_finance):
        return build_orders_assignment_impact(
            facts,
            scheduling,
            client_finance,
            self._clock.now(),
        )

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
        )
        with self._connection.cursor() as cursor:
            persist_order_lifecycle_impact(cursor, command)
            _update_order_projection(cursor, impact, payload)


def _domain_impact(candidate):
    if not isinstance(candidate, AssignmentPlanDomainImpact):
        raise TypeError("leave/substitution impact candidate is invalid")
    return candidate


def _orders_payload(impact):
    if not isinstance(impact.payload, OrdersAssignmentImpactPayload):
        raise TypeError("Orders leave/substitution impact payload is invalid")
    return impact.payload


def _update_order_projection(cursor, impact, payload):
    lifecycle = payload.lifecycle
    cursor.execute(
        "UPDATE orders SET status=%s,actual_end_date=%s,lifecycle_version=%s "
        "WHERE case_no=%s AND lifecycle_version=%s",
        (
            lifecycle.after_status.value,
            lifecycle.actual_end_date,
            impact.resulting_version,
            lifecycle.case_no,
            impact.expected_version,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("order_version_conflict")
