"""Effective workday and fresh weekly report proof for official date correction."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime
import os

import pymysql
import pytest

import infrastructure.mysql.official_service_date_correction_repository as correction_repository_module
from infrastructure.mysql.official_service_date_correction_repository import (
    MySqlOfficialServiceDateCorrectionRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.weekly_operations_report_query_adapter import (
    MySqlWeeklyOperationsReportQueryAdapter,
)
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialDateSelection,
    OfficialServiceDateCorrectionWorkflow,
)
from subsystems.reporting.weekly_operations_report_query import (
    SubsidyFacts,
    WeeklyOperationsReportQuery,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires explicitly configured disposable lu_test_* MySQL database",
)


def _connect(database):
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _seed(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO payroll_rate_policies(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
            "VALUES ('issue346-rate','citizen',300,'2026-01-01')"
        )
        cursor.execute(
            "INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) "
            "VALUES ('ISSUE-346','issue 346 client','一般市民','新竹市','東區','09:00-17:00','連續服務')"
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
            "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,"
            "service_end_time,service_end_day_offset,staff_payment_due_date,actual_start_date,actual_end_date) "
            "VALUES ('ISSUE-346',%s,'訂單完成',1,'2026-09-19','2026-09-20',"
            "2,8,0,0,'09:00:00','17:00:00',0,'2026-09-30','2026-09-19','2026-09-20')",
            (client_id,),
        )
        cursor.execute("INSERT INTO staff(name,status) VALUES ('issue 346 staff','active')")
        staff_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter) "
            "VALUES ('ISSUE-346',0,0)"
        )
        cursor.execute(
            "INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,"
            "status,effective_marker,created_by,change_reason) "
            "VALUES ('ISSUE-346',1,1,'effective',1,'fixture','original schedule')"
        )
        generation_id = int(cursor.lastrowid)
        cursor.execute(
            "UPDATE scheduling_aggregates SET aggregate_version=1,generation_counter=1,"
            "effective_generation_id=%s WHERE case_no='ISSUE-346'",
            (generation_id,),
        )
        cursor.execute(
            "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,"
            "assignment_sequence,assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
            "VALUES ('ISSUE-346',%s,'issue346-original',%s,1,'2026-09-19','2026-09-20',0,'completed')",
            (generation_id, staff_id),
        )
        assignment_id = int(cursor.lastrowid)
        for day in (date(2026, 9, 19), date(2026, 9, 20)):
            cursor.execute(
                "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,"
                "work_date,is_work_day,is_double_pay,effective_marker) "
                "VALUES ('ISSUE-346',%s,%s,%s,%s,1,0,1)",
                (staff_id, assignment_id, generation_id, day),
            )
            cursor.execute(
                "INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,"
                "generation_id,assignment_id,occupancy_type) "
                "VALUES (%s,%s,%s,%s,'assignment_interval')",
                (staff_id, day, generation_id, assignment_id),
            )
        cursor.execute(
            "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,"
            "policy_kind,hourly_rate_ntd,source_identity_status) "
            "VALUES (%s,'issue346-rate','citizen',300,'fixture')",
            (assignment_id,),
        )
        cursor.execute(
            "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('ISSUE-346',1)"
        )
        cursor.execute(
            "INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES ('ISSUE-346',1)"
        )
        cursor.execute(
            "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,"
            "direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,"
            "source_event_identity,expected_account_version,idempotency_key,actor,reason) "
            "VALUES ('issue346-client-deposit','ISSUE-346','deposit','receivable_from_client',"
            "'established',0,1600,'2026-09-30','issue346-client-source',0,"
            "'issue346-client-event','fixture','existing client obligation')"
        )
        client_event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,"
            "amount_due_ntd,due_date,status,current_event_id,projection_version) "
            "VALUES ('issue346-client-deposit','ISSUE-346','deposit','receivable_from_client',"
            "1600,'2026-09-30','open',%s,1)",
            (client_event_id,),
        )
        cursor.execute(
            "INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,"
            "staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,"
            "due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,"
            "idempotency_key,actor,reason) "
            "VALUES ('issue346-staff-service',%s,'ISSUE-346',%s,'service_pay','payable_to_staff',"
            "'established',0,4800,'2026-09-30',%s,0,1,'issue346-payroll-event','fixture',"
            "'existing staff obligation')",
            (assignment_id, staff_id, "b" * 64),
        )
        staff_event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,"
            "obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) "
            "VALUES ('issue346-staff-service',%s,'ISSUE-346',%s,'service_pay','payable_to_staff',"
            "4800,'2026-09-30','open',%s,1)",
            (assignment_id, staff_id, staff_event_id),
        )
        cursor.execute(
            "INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,"
            "after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
            "VALUES ('ISSUE-346','auto_complete','服務中','訂單完成','fixture','2026-09-20',"
            "0,'issue346-completion','{}')"
        )
        completion_event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO order_service_data_locks(case_no,lifecycle_event_id,"
            "client_settlement_fingerprint,created_by) VALUES ('ISSUE-346',%s,%s,'fixture')",
            (completion_event_id, "a" * 64),
        )
    connection.commit()
    return assignment_id, generation_id, completion_event_id


class _ReportFacts:
    def __init__(self, connection):
        self.adapter = MySqlWeeklyOperationsReportQueryAdapter(connection)

    def list_case_facts(self, start, end):
        return self.adapter.list_case_facts(start, end)

    def list_service_facts(self, start, end):
        return self.adapter.list_service_facts(start, end)

    def list_subsidy_facts(self, start, end):
        return SubsidyFacts((), ())

    def list_weekly_metrics(self, start, end):
        return []


def _weekly(connection, start=date(2026, 9, 14), end=date(2026, 9, 27)):
    connection.commit()
    report = WeeklyOperationsReportQuery(
        _ReportFacts(connection),
        lambda: datetime(2026, 9, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
    ).query(start, end)
    return {row.period_start_date: (row.weekly_work_days, row.weekly_hours)
            for row in report.service_rows if row.case_no == "ISSUE-346"}


def _weekly_staff_rows(connection):
    connection.commit()
    report = WeeklyOperationsReportQuery(
        _ReportFacts(connection),
        lambda: datetime(2026, 9, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
    ).query(date(2026, 9, 14), date(2026, 9, 27))
    return {(row.period_start_date, row.staff_name): (row.weekly_work_days, row.weekly_hours)
            for row in report.service_rows if row.case_no == "ISSUE-346"}


def _seed_substituted_staff(connection, original_assignment_id, generation_id):
    """Model the effective result of a leave substitute: day two belongs to another staff."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT staff_id FROM case_staff_assignments WHERE id=%s", (original_assignment_id,))
        original_staff_id = int(cursor.fetchone()["staff_id"])
        cursor.execute(
            "DELETE FROM scheduling_effective_occupancy WHERE generation_id=%s AND staff_id=%s "
            "AND occupancy_date='2026-09-20'", (generation_id, original_staff_id),
        )
        cursor.execute(
            "DELETE FROM staff_schedule WHERE assignment_id=%s AND work_date='2026-09-20'",
            (original_assignment_id,),
        )
        cursor.execute(
            "UPDATE case_staff_assignments SET assigned_end_date='2026-09-19' WHERE id=%s",
            (original_assignment_id,),
        )
        cursor.execute("INSERT INTO staff(name,status) VALUES ('issue 346 substitute','active')")
        substitute_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,"
            "assignment_sequence,assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
            "VALUES ('ISSUE-346',%s,'issue346-substitute',%s,2,'2026-09-20','2026-09-20',0,'completed')",
            (generation_id, substitute_id),
        )
        substitute_assignment_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,"
            "work_date,is_work_day,is_double_pay,effective_marker) "
            "VALUES ('ISSUE-346',%s,%s,%s,'2026-09-20',1,0,1)",
            (substitute_id, substitute_assignment_id, generation_id),
        )
        cursor.execute(
            "INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,generation_id,"
            "assignment_id,occupancy_type) VALUES (%s,'2026-09-20',%s,%s,'assignment_interval')",
            (substitute_id, generation_id, substitute_assignment_id),
        )
        cursor.execute(
            "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,"
            "policy_kind,hourly_rate_ntd,source_identity_status) "
            "VALUES (%s,'issue346-rate','citizen',300,'fixture')",
            (substitute_assignment_id,),
        )
    connection.commit()
    return substitute_assignment_id


def _snapshot(connection):
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT g.id,g.status,g.effective_marker FROM scheduling_generations g "
            "WHERE g.case_no='ISSUE-346' ORDER BY g.id"
        )
        generations = tuple((r["id"], r["status"], r["effective_marker"]) for r in cursor.fetchall())
        cursor.execute(
            "SELECT work_date FROM staff_schedule WHERE case_no='ISSUE-346' "
            "AND effective_marker=1 ORDER BY work_date"
        )
        dates = tuple(r["work_date"] for r in cursor.fetchall())
        counts = {}
        for table in ("client_obligations", "staff_obligations", "order_service_data_locks", "order_lifecycle_state_events"):
            cursor.execute(f"SELECT COUNT(*) total FROM {table} WHERE case_no='ISSUE-346'")
            counts[table] = int(cursor.fetchone()["total"])
        cursor.execute("SELECT actual_end_date,lifecycle_version,status FROM orders WHERE case_no='ISSUE-346'")
        order = cursor.fetchone()
    return generations, dates, counts, order


def _monetary_snapshot(connection):
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation_identity,amount_due_ntd,current_event_id FROM client_obligations "
            "WHERE case_no='ISSUE-346' ORDER BY obligation_identity"
        )
        client = tuple((row["obligation_identity"], row["amount_due_ntd"], row["current_event_id"])
                       for row in cursor.fetchall())
        cursor.execute(
            "SELECT obligation_identity,assignment_id,amount_due_ntd,current_event_id "
            "FROM staff_obligations WHERE case_no='ISSUE-346' ORDER BY obligation_identity"
        )
        staff = tuple((row["obligation_identity"], row["assignment_id"],
                       row["amount_due_ntd"], row["current_event_id"])
                      for row in cursor.fetchall())
    return client, staff


def test_completed_date_correction_updates_effective_workdays_and_fresh_weekly_report(monkeypatch):
    database = f"{DATABASE}_official_dates"
    bootstrap(Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database, confirm_database=database,
    ))
    connection = _connect(database)
    try:
        assignment_id, old_generation_id, completion_event_id = _seed(connection)
        workflow = OfficialServiceDateCorrectionWorkflow(
            MySqlOfficialServiceDateCorrectionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        assert _weekly(connection) == {date(2026, 9, 14): (2, 16)}
        before = _snapshot(connection)
        monetary_before = _monetary_snapshot(connection)
        selection = (OfficialDateSelection(assignment_id, (date(2026, 9, 19), date(2026, 9, 21))),)
        preview = workflow.preview("ISSUE-346", selection)
        assert _snapshot(connection) == before
        receipt = workflow.apply(
            "ISSUE-346", selection, expected_order_version=1,
            expected_scheduling_version=1, preview_fingerprint=preview.fingerprint.value,
            actor="issue346-admin", reason="correct service date", idempotency_key="issue346-correction-1",
            correlation_id="issue346-correction-1",
        )
        generations, dates, counts, order = _snapshot(connection)
        assert generations == ((old_generation_id, "cancelled", None), (receipt.generation_id, "effective", 1))
        assert dates == (date(2026, 9, 19), date(2026, 9, 21))
        assert counts == {"client_obligations": 1, "staff_obligations": 1,
                          "order_service_data_locks": 1, "order_lifecycle_state_events": 2}
        assert _monetary_snapshot(connection) == monetary_before
        assert order["status"] == "訂單完成" and order["actual_end_date"] == date(2026, 9, 21)
        assert _weekly(connection) == {date(2026, 9, 14): (1, 8), date(2026, 9, 21): (1, 8)}
        assert _weekly(connection, date(2026, 9, 19), date(2026, 9, 20)) == {date(2026, 9, 14): (1, 8)}
        with connection.cursor() as cursor:
            cursor.execute("SELECT lifecycle_event_id FROM order_service_data_locks WHERE case_no='ISSUE-346'")
            assert cursor.fetchone()["lifecycle_event_id"] == completion_event_id
            cursor.execute("SELECT id FROM order_lifecycle_state_events WHERE id=%s", (completion_event_id,))
            assert cursor.fetchone() is not None
        assert workflow.apply(
            "ISSUE-346", selection, expected_order_version=1,
            expected_scheduling_version=1, preview_fingerprint=preview.fingerprint.value,
            actor="issue346-admin", reason="correct service date", idempotency_key="issue346-correction-1",
            correlation_id="issue346-correction-1",
        ).generation_id == receipt.generation_id
        assert _snapshot(connection) == (generations, dates, counts, order)
        with pytest.raises(ValueError, match="official_date_version_conflict"):
            workflow.apply(
                "ISSUE-346", selection, expected_order_version=1,
                expected_scheduling_version=1, preview_fingerprint=preview.fingerprint.value,
                actor="issue346-admin", reason="stale", idempotency_key="issue346-stale",
                correlation_id="issue346-stale",
            )
        assert _snapshot(connection) == (generations, dates, counts, order)
        successor_id = receipt.effective_dates[0].assignment_id
        same_week = (OfficialDateSelection(successor_id, (date(2026, 9, 19), date(2026, 9, 22))),)
        same_week_preview = workflow.preview("ISSUE-346", same_week)
        workflow.apply(
            "ISSUE-346", same_week, expected_order_version=2,
            expected_scheduling_version=2, preview_fingerprint=same_week_preview.fingerprint.value,
            actor="issue346-admin", reason="same-week correction", idempotency_key="issue346-correction-2",
            correlation_id="issue346-correction-2",
        )
        assert _weekly(connection) == {date(2026, 9, 14): (1, 8), date(2026, 9, 21): (1, 8)}
        assert _snapshot(connection)[1] == (date(2026, 9, 19), date(2026, 9, 22))
        with pytest.raises(ValueError, match="official_date_idempotency_mismatch"):
            workflow.apply(
                "ISSUE-346", selection, expected_order_version=1,
                expected_scheduling_version=1, preview_fingerprint=preview.fingerprint.value,
                actor="issue346-admin", reason="different command", idempotency_key="issue346-correction-1",
                correlation_id="issue346-correction-1",
            )
        stable = _snapshot(connection)
        third_id = workflow.query("ISSUE-346").assignments[0].assignment_id
        third = (OfficialDateSelection(third_id, (date(2026, 9, 19), date(2026, 9, 23))),)
        third_preview = workflow.preview("ISSUE-346", third)
        with pytest.raises(ValueError, match="official_date_preview_stale"):
            workflow.apply(
                "ISSUE-346", third, expected_order_version=3,
                expected_scheduling_version=3, preview_fingerprint="f" * 64,
                actor="issue346-admin", reason="bad preview", idempotency_key="issue346-bad-preview",
                correlation_id="issue346-bad-preview",
            )
        def fail_rate_carry(*_args):
            raise RuntimeError("injected rate carry failure")
        monkeypatch.setattr(correction_repository_module, "persist_actual_start_rate_snapshot_carry", fail_rate_carry)
        with pytest.raises(RuntimeError, match="injected rate carry failure"):
            workflow.apply(
                "ISSUE-346", third, expected_order_version=3,
                expected_scheduling_version=3, preview_fingerprint=third_preview.fingerprint.value,
                actor="issue346-admin", reason="rollback proof", idempotency_key="issue346-rollback",
                correlation_id="issue346-rollback",
            )
        assert _snapshot(connection) == stable
        assert _weekly(connection) == {date(2026, 9, 14): (1, 8), date(2026, 9, 21): (1, 8)}
    finally:
        connection.close()


def test_substituted_multi_staff_dates_remain_attributed_to_correct_staff_in_fresh_weekly_report():
    database = f"{DATABASE}_substitute_dates"
    bootstrap(Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database, confirm_database=database,
    ))
    connection = _connect(database)
    try:
        original_id, old_generation_id, _ = _seed(connection)
        substitute_id = _seed_substituted_staff(connection, original_id, old_generation_id)
        workflow = OfficialServiceDateCorrectionWorkflow(
            MySqlOfficialServiceDateCorrectionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        assert _weekly_staff_rows(connection) == {
            (date(2026, 9, 14), "issue 346 staff"): (1, 8),
            (date(2026, 9, 14), "issue 346 substitute"): (1, 8),
        }
        selection = (
            OfficialDateSelection(original_id, (date(2026, 9, 19),)),
            OfficialDateSelection(substitute_id, (date(2026, 9, 21),)),
        )
        preview = workflow.preview("ISSUE-346", selection)
        receipt = workflow.apply(
            "ISSUE-346", selection, expected_order_version=1,
            expected_scheduling_version=1, preview_fingerprint=preview.fingerprint.value,
            actor="issue346-admin", reason="correct substitute service date",
            idempotency_key="issue346-substitute-correction",
            correlation_id="issue346-substitute-correction",
        )
        fresh = workflow.query("ISSUE-346")
        assert fresh.generation_id == receipt.generation_id
        assert {a.staff_name: a.service_dates for a in fresh.assignments} == {
            "issue 346 staff": (date(2026, 9, 19),),
            "issue 346 substitute": (date(2026, 9, 21),),
        }
        assert _weekly_staff_rows(connection) == {
            (date(2026, 9, 14), "issue 346 staff"): (1, 8),
            (date(2026, 9, 21), "issue 346 substitute"): (1, 8),
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM staff_schedule WHERE generation_id=%s "
                "AND effective_marker=1", (old_generation_id,),
            )
            assert cursor.fetchone()["total"] == 0
    finally:
        connection.close()
