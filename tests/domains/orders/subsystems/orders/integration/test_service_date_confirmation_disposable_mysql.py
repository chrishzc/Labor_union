"""Native MySQL contracts for Orders-owned service-date confirmation."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import hashlib
import os

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments(database: str) -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        confirm_database=database,
    )


def _connect(database: str):
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


def _seed_order(connection, case_no: str, status: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) "
            "VALUES (%s,%s,'一般市民','新竹市','東區','09:00-17:00','連續服務')",
            (case_no, f"{case_no} client"),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
            "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,service_end_time,"
            "service_end_day_offset,staff_payment_due_date,actual_start_date) "
            "VALUES (%s,%s,%s,1,'2026-09-03','2026-09-04',2,8,0,0,'09:00:00','17:00:00',0,"
            "'2026-09-18',NULL)",
            (case_no, client_id, status),
        )
        cursor.execute(
            "INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter) "
            "VALUES (%s,0,0)",
            (case_no,),
        )
    connection.commit()


def _seed_confirmed_dates(connection, case_no: str) -> None:
    digest = hashlib.sha256(f"{case_no}:dates".encode()).hexdigest()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO confirmed_service_date_versions(case_no,version,order_version,scheduling_version,"
            "service_day_count,service_date_fingerprint,is_current,confirmed_by_actor_id,reason) "
            "VALUES (%s,1,1,0,2,%s,1,'fixture','historical fixture')",
            (case_no, digest),
        )
        version_id = int(cursor.lastrowid)
        cursor.executemany(
            "INSERT INTO confirmed_service_date_days(confirmed_version_id,ordinal,service_date) "
            "VALUES (%s,%s,%s)",
            [
                (version_id, 1, date(2026, 9, 3)),
                (version_id, 2, date(2026, 9, 4)),
            ],
        )
    connection.commit()


def _workflow(connection):
    from infrastructure.mysql.matching_schedule_confirmation_repository import (
        MySqlMatchingScheduleConfirmationRepository,
    )
    from infrastructure.mysql.service_date_confirmation_repository import (
        MySqlServiceDateConfirmationRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.service_date_confirmation_workflow import (
        ServiceDateConfirmationWorkflow,
    )

    return ServiceDateConfirmationWorkflow(
        MySqlServiceDateConfirmationRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        MySqlMatchingScheduleConfirmationRepository(connection),
    )


def _read_rows(cursor, sql: str, case_no: str) -> tuple[tuple[object, ...], ...]:
    cursor.execute(sql, (case_no,))
    return tuple(tuple(row.values()) for row in cursor.fetchall())


def _owner_snapshot(connection, case_no: str) -> dict[str, tuple[tuple[object, ...], ...]]:
    with connection.cursor() as cursor:
        return {
            "order": _read_rows(
                cursor,
                "SELECT status,lifecycle_version,actual_start_date FROM orders WHERE case_no=%s",
                case_no,
            ),
            "aggregate": _read_rows(
                cursor,
                "SELECT aggregate_version,generation_counter,effective_generation_id "
                "FROM scheduling_aggregates WHERE case_no=%s",
                case_no,
            ),
            "versions": _read_rows(
                cursor,
                "SELECT version,order_version,scheduling_version,service_day_count,is_current,"
                "confirmed_by_actor_id,reason FROM confirmed_service_date_versions "
                "WHERE case_no=%s ORDER BY version",
                case_no,
            ),
            "days": _read_rows(
                cursor,
                "SELECT version.version,day.ordinal,day.service_date "
                "FROM confirmed_service_date_versions version "
                "JOIN confirmed_service_date_days day ON day.confirmed_version_id=version.id "
                "WHERE version.case_no=%s ORDER BY version.version,day.ordinal",
                case_no,
            ),
            "receipts": _read_rows(
                cursor,
                "SELECT version.version,receipt.idempotency_key,receipt.actor_id "
                "FROM confirmed_service_date_receipts receipt "
                "JOIN confirmed_service_date_versions version ON version.id=receipt.confirmed_version_id "
                "WHERE version.case_no=%s ORDER BY receipt.id",
                case_no,
            ),
            "generations": _read_rows(
                cursor,
                "SELECT generation_number,status,effective_marker FROM scheduling_generations "
                "WHERE case_no=%s ORDER BY generation_number",
                case_no,
            ),
            "assignments": _read_rows(
                cursor,
                "SELECT assignment_sequence,status,generation_id FROM case_staff_assignments "
                "WHERE case_no=%s ORDER BY id",
                case_no,
            ),
            "schedule": _read_rows(
                cursor,
                "SELECT schedule.work_date,schedule.is_work_day,schedule.effective_marker "
                "FROM staff_schedule schedule JOIN case_staff_assignments assignment "
                "ON assignment.id=schedule.assignment_id WHERE assignment.case_no=%s "
                "ORDER BY schedule.id",
                case_no,
            ),
            "restart_receipts": _read_rows(
                cursor,
                "SELECT command_family,idempotency_key,resulting_generation_id "
                "FROM scheduling_command_receipts WHERE case_no=%s "
                "AND command_family='orders_historical_precision_restart' ORDER BY id",
                case_no,
            ),
        }


def test_normal_order_confirmation_persists_once_and_replays_exactly() -> None:
    database = f"{DATABASE}_normal_dates"
    bootstrap(_arguments(database))
    connection = _connect(database)
    case_no = "NORMAL-DATES-001"
    try:
        _seed_order(connection, case_no, "訂單成立")
        workflow = _workflow(connection)
        dates = (date(2026, 9, 3), date(2026, 9, 4))

        before = _owner_snapshot(connection, case_no)
        facts = workflow.query(case_no)
        preview = workflow.preview(case_no, dates)
        assert _owner_snapshot(connection, case_no) == before
        assert facts.current_version is None
        assert facts.current_dates == ()
        assert facts.suggested_dates == ()
        assert facts.selectable_dates[:2] == dates

        arguments = dict(
            expected_order_version=facts.order_version,
            expected_scheduling_version=facts.scheduling_version,
            preview_fingerprint=preview.candidate.fingerprint.value,
            actor="issue-318-test",
            reason="normal order service dates",
            idempotency_key=f"{case_no}-dates",
        )
        receipt = workflow.apply(case_no, dates, **arguments)
        after_apply = _owner_snapshot(connection, case_no)
        replay = workflow.apply(case_no, dates, **arguments)

        assert replay == receipt
        assert _owner_snapshot(connection, case_no) == after_apply
        assert receipt.confirmed_version == 1
        assert receipt.service_dates == dates
        assert after_apply["order"] == (("訂單成立", 1, None),)
        assert after_apply["aggregate"] == ((0, 0, None),)
        assert after_apply["versions"] == (
            (1, 1, 0, 2, 1, "issue-318-test", "normal order service dates"),
        )
        assert after_apply["days"] == (
            (1, 1, date(2026, 9, 3)),
            (1, 2, date(2026, 9, 4)),
        )
        assert after_apply["receipts"] == ((1, f"{case_no}-dates", "issue-318-test"),)
        assert after_apply["generations"] == ()
        assert after_apply["assignments"] == ()
        assert after_apply["schedule"] == ()
        current = workflow.query(case_no)
        assert current.current_version == 1
        assert current.current_dates == dates
    finally:
        connection.close()


def test_unrestarted_historical_query_refresh_is_zero_write() -> None:
    database = f"{DATABASE}_historical_read"
    bootstrap(_arguments(database))
    connection = _connect(database)
    case_no = "HISTORY-READ-001"
    try:
        _seed_order(connection, case_no, "歷史訂單－未服務")
        _seed_confirmed_dates(connection, case_no)
        workflow = _workflow(connection)
        before = _owner_snapshot(connection, case_no)

        first = workflow.query(case_no)
        refreshed = workflow.query(case_no)

        assert first == refreshed
        assert first.current_version == 1
        assert first.current_dates == (date(2026, 9, 3), date(2026, 9, 4))
        assert first.restart_generation_number is None
        assert first.restart_assignments == ()
        assert _owner_snapshot(connection, case_no) == before
        assert before["order"] == (("歷史訂單－未服務", 1, None),)
        assert before["generations"] == ()
        assert before["assignments"] == ()
        assert before["schedule"] == ()
        assert before["restart_receipts"] == ()
    finally:
        connection.close()
