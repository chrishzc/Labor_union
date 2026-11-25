"""Reprice both unpaid owners inside Holiday Maintenance's existing transaction."""
from __future__ import annotations

from decimal import Decimal
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
from infrastructure.mysql.order_terms_read_model import (
    _select_client_obligations, load_calculable_client_finance_facts, select_order,
)
from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository, _load_obligations
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
from subsystems.scheduling.holiday_maintenance import HolidayCommand


def load_frozen_holiday_amounts(cursor: DictCursor, case_no: str, *, lock: bool = False) -> tuple[int, int] | None:
    suffix = " FOR UPDATE" if lock else ""
    for table in ("client_finance_accounts", "payroll_case_accounts"):
        cursor.execute(f"SELECT aggregate_version FROM {table} WHERE case_no=%s" + suffix, (case_no,))
        cursor.fetchone()
    cursor.execute("SELECT id FROM client_ledger_entries WHERE case_no=%s ORDER BY id" + suffix, (case_no,))
    client_history = bool(cursor.fetchall())
    staff = _load_obligations(cursor, case_no, lock)
    if not client_history and not any(row["payout_history_exists"] for row in staff):
        return None
    client = _select_client_obligations(cursor, case_no, lock)
    return (sum(int(row["contracted_amount_ntd"]) for row in client),
            sum(int(row["effective_contractual_amount_ntd"]) for row in staff))


class MySqlHolidayRepricing:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def __call__(self, command: HolidayCommand, key: str, actor: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT assignment.case_no FROM staff_schedule schedule "
                "JOIN case_staff_assignments assignment ON assignment.id=schedule.assignment_id "
                "JOIN scheduling_aggregates aggregate ON aggregate.case_no=assignment.case_no "
                "AND aggregate.effective_generation_id=schedule.generation_id "
                "WHERE schedule.work_date=%s AND schedule.is_work_day=1 AND schedule.effective_marker=1 "
                "ORDER BY assignment.case_no", (command.holiday_date,),
            )
            cases = tuple(str(row["case_no"]) for row in cursor.fetchall())
            for case_no in cases:
                self.reprice_case(case_no, key, actor)

    def reprice_case(self, case_no: str, key: str, actor: str) -> None:
        with self._connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=True)
            if str(order["status"]).startswith("歷史"):
                return
            if load_frozen_holiday_amounts(cursor, case_no, lock=True) is not None:
                return
            facts, _ = load_calculable_client_finance_facts(cursor, order, lock=True, allow_planned=False)
            if facts is None:
                return
            premium_exists = any(day.holiday_hours for day in facts.charge_days)
            if premium_exists and facts.pricing is not None and facts.pricing.is_full_subsidy(
                Decimal(len(facts.charge_days)) * Decimal(str(facts.service_hours_per_day)),
            ) is True:
                return
            child = fingerprint_payload({"holiday": key, "case": case_no}).value
            candidate = build_client_finance_terms_candidate(facts, f"holiday:{child}")
            if candidate.blockers:
                return
            identity = IdempotencyKey(child)
            context = ActorContext(actor)
            correlation = CorrelationId(child)
            persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(
                candidate, identity, context, "國定假日雙倍設定同步", correlation, "holiday", child,
            ), synchronize_government=False)
            workflow = PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(self._connection), lambda: None)
            workflow.synchronize_in_unit_of_work(case_no, actor=context, key=identity, correlation_id=correlation)
