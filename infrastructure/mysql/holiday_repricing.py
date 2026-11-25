"""Reprice both unpaid owners inside Holiday Maintenance's existing transaction."""
from __future__ import annotations

from dataclasses import replace
import json
import re
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from domains.client_finance.obligation_planning import build_client_finance_terms_candidate, _holiday_funding_pending
from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
from infrastructure.mysql.order_terms_read_model import (
    _select_client_obligations, is_holiday_pricing_excluded, load_calculable_client_finance_facts, select_order,
)
from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository, _load_obligations
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
from subsystems.scheduling.holiday_maintenance import HolidayCaseRepricingResult, HolidayCommand, HolidayRepricingOutcome


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
        self._prepare_errors: dict[str, HolidayCaseRepricingResult] = {}

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
                if is_holiday_pricing_excluded(cursor, order, lock=True):
                    continue
                self.prepare_case(case_no)

    def prepare_case(self, case_no: str) -> int | None:
        from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
        from subsystems.client_finance.pricing_configuration import case_total_amount
        try:
            with self._connection.cursor(DictCursor) as cursor:
                if load_frozen_holiday_amounts(cursor, case_no, lock=True) is None:
                    return None
                previous = load_frozen_holiday_case_total(cursor, case_no)
                if previous is None:
                    facts = MySqlPricingConfigurationRepository(self._connection).case(case_no, lock=True)
                    previous = case_total_amount(replace(facts, frozen_amounts=None))
                if previous is not None:
                    self._before_totals[case_no] = previous
                return previous
        except ValueError as error:
            self._prepare_errors[case_no] = HolidayCaseRepricingResult(case_no, "failed",
                reason_code=_reason_code(error), missing_mapping=_missing_mapping(error))
            return None

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
            cursor.execute("SAVEPOINT holiday_case_repricing")
            try:
                result = self._reprice_case(case_no, key, actor)
            except Exception as error:
                cursor.execute("ROLLBACK TO SAVEPOINT holiday_case_repricing")
                result = HolidayCaseRepricingResult(case_no, "failed", reason_code=_reason_code(error),
                    missing_mapping=_missing_mapping(error))
            cursor.execute("RELEASE SAVEPOINT holiday_case_repricing")
            return result

    def _reprice_case(self, case_no: str, key: str, actor: str) -> HolidayCaseRepricingResult:
        with self._connection.cursor(DictCursor) as cursor:
            order = select_order(cursor, case_no, lock=True)
            if is_holiday_pricing_excluded(cursor, order, lock=True):
                return HolidayCaseRepricingResult(case_no, "historical_excluded", reason_code="historical_source_excluded")
            frozen = load_frozen_holiday_amounts(cursor, case_no, lock=True)
            if frozen is not None:
                saved_total = self._before_totals.get(case_no)
                if saved_total is None:
                    saved_total = load_frozen_holiday_case_total(cursor, case_no)
                preparation = self._prepare_errors.get(case_no)
                return HolidayCaseRepricingResult(case_no, "preserved_cash_history", saved_total,
                    "formal_cash_history_exists", frozen[0], frozen[1],
                    missing_mapping=preparation.missing_mapping if preparation else ())
            if case_no in self._prepare_errors:
                return self._prepare_errors[case_no]
            facts, _ = load_calculable_client_finance_facts(cursor, order, lock=True, allow_planned=False)
            if facts is None:
                return HolidayCaseRepricingResult(case_no, "blocked", reason_code="service_facts_unavailable")
            premium_exists = any(day.is_double_pay or day.holiday_hours for day in facts.charge_days)
            funding_pending = premium_exists and _holiday_funding_pending(facts)
            before = self._recorded_amounts(cursor, case_no)
            child = fingerprint_payload({"holiday": key, "case": case_no}).value
            candidate = build_client_finance_terms_candidate(facts, f"holiday:{child}")
            if candidate.blockers:
                return HolidayCaseRepricingResult(case_no, "blocked", reason_code=candidate.blockers[0])
            identity = IdempotencyKey(child)
            context = ActorContext(actor)
            correlation = CorrelationId(child)
            persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(
                candidate, identity, context, "國定假日雙倍設定同步", correlation, "holiday", child,
            ), synchronize_government=False)
            workflow = PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(self._connection), lambda: MySqlUnitOfWork(self._connection))
            workflow.synchronize_in_unit_of_work(case_no, actor=context, key=identity, correlation_id=correlation)
            if funding_pending:
                return self._result(case_no, "repriced_funding_pending", "holiday_funding_assignment_pending")
            after = self._recorded_amounts(cursor, case_no)
            return self._result(case_no, "unchanged" if before == after else "repriced",
                                "pricing_amounts_unchanged" if before == after else None)

    @staticmethod
    def _recorded_amounts(cursor: DictCursor, case_no: str) -> tuple[int, int]:
        client = _select_client_obligations(cursor, case_no, True)
        staff = _load_obligations(cursor, case_no, True)
        return (sum(int(row["contracted_amount_ntd"]) for row in client),
                sum(int(row["effective_contractual_amount_ntd"]) for row in staff))

    def _result(self, case_no: str, outcome: HolidayRepricingOutcome, reason: str | None) -> HolidayCaseRepricingResult:
        from infrastructure.mysql.government_subsidy_period_repository import query_case_subsidy_amount
        from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
        from subsystems.client_finance.pricing_configuration import current_pricing_impact
        facts = MySqlPricingConfigurationRepository(self._connection).case(case_no, lock=True)
        if case_no in self._before_totals:
            facts = replace(facts, frozen_case_total=self._before_totals[case_no])
        impact = current_pricing_impact(facts)
        if impact.case_total_amount is None or impact.client_amount is None:
            raise ValueError("service_facts_unavailable")
        subsidy = query_case_subsidy_amount(self._connection, case_no, lock=True).amount_ntd
        unallocated = (max(0, impact.case_total_amount - impact.client_amount - subsidy)
                       if subsidy is not None else None)
        return HolidayCaseRepricingResult(case_no, outcome, impact.case_total_amount, reason,
            impact.client_amount, impact.staff_total_amount, subsidy, unallocated)


def _reason_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if code is None and isinstance(error, ValueError) and error.args:
        code = error.args[0]
    if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,119}", code):
        return code
    return "holiday_recalculation_failed"


def _missing_mapping(error: Exception) -> tuple[str, ...]:
    missing = getattr(error, "missing_mapping", ())
    return tuple(item for item in missing if isinstance(item, str)) if isinstance(missing, tuple) else ()
