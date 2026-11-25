"""Reprice both unpaid owners inside Holiday Maintenance's existing transaction."""
from __future__ import annotations

from decimal import Decimal
from dataclasses import replace
import json
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
from infrastructure.mysql.order_terms_read_model import (
    _select_client_obligations, load_calculable_client_finance_facts, select_order,
)
from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository, _load_obligations
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
from subsystems.scheduling.holiday_maintenance import HolidayCaseRepricingResult, HolidayCommand


def load_frozen_holiday_amounts(cursor: DictCursor, case_no: str, *, lock: bool = False) -> tuple[int, int] | None:
    suffix = " FOR UPDATE" if lock else ""
    for table in ("client_finance_accounts", "payroll_case_accounts"):
        cursor.execute(f"SELECT aggregate_version FROM {table} WHERE case_no=%s" + suffix, (case_no,))
        cursor.fetchone()
    cursor.execute("SELECT id FROM client_ledger_entries WHERE case_no=%s ORDER BY id" + suffix, (case_no,))
    client_history = bool(cursor.fetchall())
    staff = _load_obligations(cursor, case_no, lock)
    client = _select_client_obligations(cursor, case_no, lock)
    cursor.execute("SELECT links.payout_event_id FROM staff_payout_obligation_links links "
                   "JOIN staff_obligations obligation ON obligation.obligation_identity=links.obligation_identity "
                   "WHERE obligation.case_no=%s ORDER BY links.payout_event_id" + suffix, (case_no,))
    staff_history = bool(cursor.fetchall())
    if not (client_history or staff_history or any(row["formal_history_exists"] for row in client)
            or any(row["payout_history_exists"] for row in staff)):
        return None
    return (sum(int(row["contracted_amount_ntd"]) for row in client),
            sum(int(row["effective_contractual_amount_ntd"]) for row in staff))



def load_frozen_holiday_case_total(cursor: DictCursor, case_no: str) -> int | None:
    cursor.execute("SELECT result_snapshot FROM admin_command_receipts "
                   "WHERE command_family=%s ORDER BY id DESC", ("scheduling_holiday_maintenance/v2",))
    for row in cursor.fetchall():
        payload = row["result_snapshot"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        for result in payload.get("case_results", ()):
            if result["case_no"] == case_no and result.get("case_total_amount") is not None:
                return int(result["case_total_amount"])
    cursor.execute("SELECT result_snapshot FROM service_date_adjustment_receipts WHERE case_no=%s ORDER BY id DESC", (case_no,))
    for row in cursor.fetchall():
        payload = row["result_snapshot"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if payload.get("frozen_case_total_amount") is not None:
            return int(payload["frozen_case_total_amount"])
    return None


class MySqlHolidayRepricing:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._before_totals: dict[str, int] = {}

    def prepare(self, command: HolidayCommand) -> None:
        with self._connection.cursor(DictCursor) as cursor:
            cursor.execute("SELECT DISTINCT assignment.case_no FROM staff_schedule schedule "
                "JOIN case_staff_assignments assignment ON assignment.id=schedule.assignment_id "
                "JOIN scheduling_aggregates aggregate ON aggregate.case_no=assignment.case_no "
                "AND aggregate.effective_generation_id=schedule.generation_id "
                "WHERE schedule.work_date=%s AND schedule.is_work_day=1 AND schedule.effective_marker=1 "
                "ORDER BY assignment.case_no", (command.holiday_date,))
            cases = tuple(str(row["case_no"]) for row in cursor.fetchall())
            for case_no in cases:
                order = select_order(cursor, case_no, lock=True)
                if str(order["status"]).startswith("歷史"):
                    continue
                self.prepare_case(case_no)

    def prepare_case(self, case_no: str) -> int | None:
        from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
        from subsystems.client_finance.pricing_configuration import case_total_amount
        with self._connection.cursor(DictCursor) as cursor:
            if load_frozen_holiday_amounts(cursor, case_no, lock=True) is None:
                return None
            previous = load_frozen_holiday_case_total(cursor, case_no)
            if previous is None:
                facts = MySqlPricingConfigurationRepository(self._connection).case(case_no, lock=True)
                previous = case_total_amount(replace(facts, frozen_amounts=None))
            self._before_totals[case_no] = previous
            return previous

    def __call__(self, command: HolidayCommand, key: str, actor: str) -> tuple[HolidayCaseRepricingResult, ...]:
        with self._connection.cursor(DictCursor) as cursor:
            cursor.execute(
                "SELECT DISTINCT assignment.case_no FROM staff_schedule schedule "
                "JOIN case_staff_assignments assignment ON assignment.id=schedule.assignment_id "
                "JOIN scheduling_aggregates aggregate ON aggregate.case_no=assignment.case_no "
                "AND aggregate.effective_generation_id=schedule.generation_id "
                "WHERE schedule.work_date=%s AND schedule.is_work_day=1 AND schedule.effective_marker=1 "
                "ORDER BY assignment.case_no", (command.holiday_date,),
            )
            cases = tuple(str(row["case_no"]) for row in cursor.fetchall())
            return tuple(self.reprice_case(case_no, key, actor) for case_no in cases)

    def reprice_case(self, case_no: str, key: str, actor: str) -> HolidayCaseRepricingResult:
        with self._connection.cursor(DictCursor) as cursor:
            order = select_order(cursor, case_no, lock=True)
            if str(order["status"]).startswith("歷史"):
                return HolidayCaseRepricingResult(case_no, "historical_excluded")
            if load_frozen_holiday_amounts(cursor, case_no, lock=True) is not None:
                return HolidayCaseRepricingResult(case_no, "preserved_cash_history", self._before_totals.get(case_no))
            facts, _ = load_calculable_client_finance_facts(cursor, order, lock=True, allow_planned=False)
            if facts is None:
                return HolidayCaseRepricingResult(case_no, "unchanged")
            premium_exists = any(day.holiday_hours for day in facts.charge_days)
            if premium_exists and facts.pricing is not None and facts.pricing.is_full_subsidy(
                Decimal(len(facts.charge_days)) * Decimal(str(facts.service_hours_per_day)),
            ) is True:
                return HolidayCaseRepricingResult(case_no, "funding_decision_pending")
            child = fingerprint_payload({"holiday": key, "case": case_no}).value
            candidate = build_client_finance_terms_candidate(facts, f"holiday:{child}")
            if candidate.blockers:
                return HolidayCaseRepricingResult(case_no, "blocked")
            identity = IdempotencyKey(child)
            context = ActorContext(actor)
            correlation = CorrelationId(child)
            persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(
                candidate, identity, context, "國定假日雙倍設定同步", correlation, "holiday", child,
            ), synchronize_government=False)
            workflow = PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(self._connection), lambda: MySqlUnitOfWork(self._connection))
            workflow.synchronize_in_unit_of_work(case_no, actor=context, key=identity, correlation_id=correlation)
            return HolidayCaseRepricingResult(case_no, "repriced")
