"""
File: test_order_auto_completion_durable_worker_e2e.py
Description: 以 disposable MySQL 驗證 Orders Auto Completion Bridge discovery 與 canonical worker。
"""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments():
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def test_due_order_is_enqueued_then_completed_only_by_the_canonical_durable_worker():
    bootstrap(_arguments())
    _seed_due_order()

    receipt = _dispatch("2026-08-04T18:00:00+08:00")
    assert receipt.scanned_count == 1
    assert receipt.enqueued_count == 1
    assert receipt.duplicate_count == 0
    job_id = _single_job_id()
    assert _job_status(job_id) == "queued"

    assert _run_worker_once() is True
    assert _job_status(job_id) == "succeeded"
    assert _order_state() == ("訂單完成", 1)
    assert _count("order_auto_completion_apply_receipts") == 1
    assert _count("orders_domain_outbox") == 1

    repeated = _dispatch("2026-08-04T19:00:00+08:00")
    assert repeated.scanned_count == 0
    assert _count("background_jobs") == 1


def test_incomplete_schedule_is_not_discovered_or_reported_as_a_successful_completion():
    bootstrap(_arguments())
    _seed_due_order(service_day_count=2)

    receipt = _dispatch("2026-08-04T18:00:00+08:00")

    assert receipt.scanned_count == 0
    assert _count("background_jobs") == 0
    assert _order_state() == ("服務中", 0)
    assert _count("order_auto_completion_apply_receipts") == 0


def _dispatch(value):
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_auto_completion_job_repository import (
        MySqlDueOrderAutoCompletionRepository,
    )
    from subsystems.orders.auto_completion_job_dispatch import AutoCompletionJobDispatcher
    from subsystems.jobs.command_application import DurableJobCommandApplication

    connection = get_connection()
    try:
        return AutoCompletionJobDispatcher(
            MySqlDueOrderAutoCompletionRepository(connection),
            DurableJobCommandApplication(BackgroundJobRepository(connection), connection),
        ).dispatch_due_orders(datetime.fromisoformat(value))
    finally:
        connection.close()


def _run_worker_once():
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    connection = get_connection()
    try:
        worker = DurableJobWorker(
            BackgroundJobRepository(connection),
            connection,
            default_job_handlers(),
            "g05-durable-e2e-worker",
            retry_delay_seconds=0,
        )
        return worker.recover_and_run_once()
    finally:
        connection.close()


def _seed_due_order(service_day_count=1):
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('G05-JOB','G05 Job Client')")
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES ('G05 Job Staff','active')")
            staff_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orders "
                "(case_no,client_id,status,lifecycle_version,start_date,service_days,"
                "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
                "service_end_day_offset,actual_start_date,actual_end_date,staff_payment_due_date) "
                "VALUES ('G05-JOB',%s,'服務中',0,'2026-08-01',%s,8,0,'09:00:00','17:00:00',0,"
                "'2026-08-01','2026-08-04','2026-08-15')",
                (client_id, service_day_count),
            )
            cursor.execute(
                "INSERT INTO scheduling_generations "
                "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
                "VALUES ('G05-JOB',1,1,'effective',1,'g05-job-e2e','fixture')"
            )
            generation_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO scheduling_aggregates "
                "(case_no,aggregate_version,generation_counter,effective_generation_id) "
                "VALUES ('G05-JOB',1,1,%s)",
                (generation_id,),
            )
            cursor.execute(
                "INSERT INTO case_staff_assignments "
                "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
                "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
                "VALUES ('G05-JOB',%s,'G05-JOB:g1:a1',%s,1,'2026-08-04','2026-08-04',0,'planned')",
                (generation_id, staff_id),
            )
            assignment_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO staff_schedule "
                "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) "
                "VALUES ('G05-JOB',%s,%s,%s,'2026-08-04',1,0,1)",
                (staff_id, assignment_id, generation_id),
            )
        connection.commit()
    finally:
        connection.close()


def _single_job_id():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT job_id FROM background_jobs")
            return str(cursor.fetchone()["job_id"])
    finally:
        connection.close()


def _job_status(job_id):
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        job = BackgroundJobRepository(connection).get_job(job_id)
        return job.status if job else None
    finally:
        connection.close()


def _order_state():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status,lifecycle_version FROM orders WHERE case_no='G05-JOB'")
            row = cursor.fetchone()
            return str(row["status"]), int(row["lifecycle_version"])
    finally:
        connection.close()


def _count(table):
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
            return int(cursor.fetchone()["count"])
    finally:
        connection.close()
