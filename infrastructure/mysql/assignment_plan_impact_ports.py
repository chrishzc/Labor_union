"""MySQL-backed cross-Domain ports for Assignment Plan."""

from __future__ import annotations

from typing import Any

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


class MySqlClientFinanceAssignmentImpactPort:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview_assignment_plan(self, facts, scheduling):
        return build_client_finance_assignment_impact(facts, scheduling)

    def persist_assignment_plan(
        self,
        candidate,
        context,
        scheduling_result,
    ) -> None:
        impact = _domain_impact(candidate)
        command = ClientFinanceImpactPersistenceCommand(
            candidate=impact.payload,
            idempotency_key=context.idempotency_key,
            actor=context.actor,
            reason=context.reason,
            correlation_id=context.correlation_id,
            source_event_family="assignment-plan",
            source_event_id=scheduling_result.rebuild_event_id,
        )
        with self._connection.cursor() as cursor:
            persist_client_finance_terms_impact(cursor, command)


class MySqlPayrollAssignmentImpactPort:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview_assignment_plan(self, facts, scheduling):
        return build_payroll_assignment_impact(facts, scheduling)

    def persist_assignment_plan(
        self,
        candidate,
        context,
        scheduling_result,
    ) -> None:
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


class MySqlOrdersAssignmentImpactPort:
    def __init__(self, connection: Any, clock: BusinessClock) -> None:
        self._connection = connection
        self._clock = clock

    def preview_assignment_plan(
        self,
        facts,
        scheduling,
        client_finance,
    ):
        return build_orders_assignment_impact(
            facts,
            scheduling,
            client_finance,
            self._clock.now(),
        )

    def persist_assignment_plan(
        self,
        candidate,
        context,
        scheduling_result,
    ) -> None:
        del scheduling_result
        impact = _domain_impact(candidate)
        payload = _orders_payload(impact)
        command = _lifecycle_command(impact, payload, context)
        with self._connection.cursor() as cursor:
            persist_order_lifecycle_impact(cursor, command)
            persist_order_lifecycle_projection(cursor, command)


def _lifecycle_command(impact, payload, context):
    return LifecycleImpactPersistenceCommand(
        candidate=payload.lifecycle,
        expected_order_version=impact.expected_version,
        resulting_order_version=impact.resulting_version,
        client_settlement_fingerprint=(
            payload.client_settlement_fingerprint
        ),
        idempotency_key=context.idempotency_key,
        actor=context.actor,
        reason=context.reason,
        correlation_id=context.correlation_id,
        trigger_event="assignment_plan_applied",
    )


def _domain_impact(candidate) -> AssignmentPlanDomainImpact:
    if not isinstance(candidate, AssignmentPlanDomainImpact):
        raise TypeError("assignment impact candidate is invalid")
    return candidate


def _orders_payload(
    impact: AssignmentPlanDomainImpact,
) -> OrdersAssignmentImpactPayload:
    if not isinstance(impact.payload, OrdersAssignmentImpactPayload):
        raise TypeError("Orders assignment impact payload is invalid")
    return impact.payload
