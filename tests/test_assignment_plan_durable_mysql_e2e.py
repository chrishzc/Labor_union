"""
File: test_assignment_plan_durable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Assignment Plan Bridge replay、crash recovery 與單次 Domain Apply。
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _seed_waiting_lock_case(connection) -> int:
    """Keep this explicit because the proof starts from canonical domain facts."""
    case_no = "AP-DURABLE-1"
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients (case_no,name,identity_status) VALUES (%s,%s,%s)",
            (case_no, "Durable Client", "\u4e00\u822c\u5e02\u6c11"),
        )
        client_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO staff (name,status) VALUES (%s,'active')", ("Durable Staff",)
        )
        staff_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO orders (case_no,client_id,status,lifecycle_version,start_date,"
            "end_date,service_days,service_hours_per_day,floor_fee,service_start_time,"
            "service_end_time,service_end_day_offset,staff_payment_due_date) "
            "VALUES (%s,%s,%s,0,%s,%s,2,8,0,%s,%s,0,%s)",
            (case_no, client_id, "\u6d3d\u8ac7\u4e2d", date(2026, 8, 1), date(2026, 8, 2),
             "09:00:00", "17:00:00", date(2026, 8, 15)),
        )
        cursor.execute(
            "INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,0)",
            (case_no,),
        )
        cursor.execute(
            "INSERT INTO client_payment_terms_events (case_no,policy_version,client_hourly_rate_ntd,"
            "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,"
            "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
            "VALUES (%s,'terms-v1',300,1,%s,%s,%s,0,%s,%s,'test','fixture')",
            (case_no, date(2026, 7, 20), date(2026, 8, 1), date(2026, 8, 2),
             f"{case_no}-terms-source", f"{case_no}-terms-idem"),
        )
        terms_event_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO client_payment_terms (case_no,policy_version,client_hourly_rate_ntd,"
            "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,"
            "current_event_id) VALUES (%s,'terms-v1',300,1,%s,%s,%s,%s)",
            (case_no, date(2026, 7, 20), date(2026, 8, 1), date(2026, 8, 2), terms_event_id),
        )
        _seed_payroll_and_contract(cursor, case_no, terms_event_id)
        _seed_waiting_lock(cursor, case_no, staff_id)
        _seed_settled_deposit(cursor, case_no)
    connection.commit()
    return staff_id


def _seed_payroll_and_contract(cursor, case_no, terms_event_id) -> None:
    cursor.execute(
        "INSERT INTO case_architecture_bootstrap_events (case_no,order_version,"
        "client_payment_terms_event_id,client_policy_version,client_hourly_rate_ntd,"
        "payroll_policy_version,payroll_policy_kind,payroll_hourly_rate_ntd,"
        "source_identity_status,candidate_fingerprint,idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,0,%s,'terms-v1',300,'approved-rates-v1','citizen',300,%s,%s,%s,"
        "'test','fixture',%s)",
        (case_no, terms_event_id, "\u4e00\u822c\u5e02\u6c11", "a" * 64,
         f"{case_no}-bootstrap", f"{case_no}-corr"),
    )
    bootstrap_event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO case_payroll_rate_policy_snapshots (case_no,policy_version,policy_kind,"
        "hourly_rate_ntd,source_identity_status,source_event_id) VALUES (%s,'approved-rates-v1',"
        "'citizen',300,%s,%s)",
        (case_no, "\u4e00\u822c\u5e02\u6c11", bootstrap_event_id),
    )
    cursor.execute("INSERT INTO payroll_case_accounts (case_no,aggregate_version) VALUES (%s,0)", (case_no,))
    cursor.execute(
        "INSERT INTO scheduling_aggregates (case_no,aggregate_version,generation_counter) VALUES (%s,0,0)",
        (case_no,),
    )
    cursor.execute(
        "INSERT INTO order_contract_flow_events (case_no,contract_identity,event_type,actor,reason,idempotency_key) "
        "VALUES (%s,%s,'contract_completed','test','fixture',%s)",
        (case_no, f"{case_no}-contract", f"{case_no}-contract-idem"),
    )


def _seed_waiting_lock(cursor, case_no, staff_id) -> None:
    cursor.execute(
        "INSERT INTO caregiver_matching_plans (case_no,version,status,is_active,start_date,end_date,created_by) "
        "VALUES (%s,1,'proposed',1,%s,%s,'test')",
        (case_no, date(2026, 8, 1), date(2026, 8, 2)),
    )
    plan_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO caregiver_matching_plan_segments (plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
        "VALUES (%s,1,%s,%s,%s)",
        (plan_id, staff_id, date(2026, 8, 1), date(2026, 8, 2)),
    )
    segment_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO precontract_service_commitments "
        "(case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) "
        "VALUES (%s,%s,%s,%s,'test')",
        (case_no, plan_id, f"{case_no}-commitment", "c" * 64),
    )
    commitment_id = cursor.lastrowid
    for service_date in (date(2026, 8, 1), date(2026, 8, 2)):
        cursor.execute(
            "INSERT INTO precontract_service_commitment_days "
            "(commitment_id,matching_segment_id,staff_id,service_date) VALUES (%s,%s,%s,%s)",
            (commitment_id, segment_id, staff_id, service_date),
        )
    cursor.execute(
        "INSERT INTO caregiver_availability_locks (plan_id,status,is_active,created_by) VALUES (%s,'active',1,'test')",
        (plan_id,),
    )
    lock_id = cursor.lastrowid
    for lock_date in (date(2026, 8, 1), date(2026, 8, 2)):
        cursor.execute(
            "INSERT INTO caregiver_availability_lock_days (lock_id,segment_id,staff_id,lock_date,active_marker) "
            "VALUES (%s,%s,%s,%s,1)",
            (lock_id, segment_id, staff_id, lock_date),
        )
    cursor.execute(
        "INSERT INTO confirmed_service_date_versions "
        "(case_no,version,order_version,scheduling_version,service_day_count,"
        "service_date_fingerprint,is_current,confirmed_by_actor_id,reason) "
        "VALUES (%s,1,0,0,2,%s,1,'test','durable fixture')",
        (case_no, "d" * 64),
    )
    confirmed_version_id = cursor.lastrowid
    for ordinal, service_date in enumerate((date(2026, 8, 1), date(2026, 8, 2)), start=1):
        cursor.execute(
            "INSERT INTO confirmed_service_date_days "
            "(confirmed_version_id,ordinal,service_date) VALUES (%s,%s,%s)",
            (confirmed_version_id, ordinal, service_date),
        )
    cursor.execute(
        "INSERT INTO matching_schedule_snapshots "
        "(case_no,plan_id,confirmed_version_id,snapshot_fingerprint,status,current_marker,"
        "created_by_actor_id) VALUES (%s,%s,%s,%s,'sent',1,'test')",
        (case_no, plan_id, confirmed_version_id, "e" * 64),
    )
    snapshot_id = cursor.lastrowid
    for audience_type, recipient_key, recipient_segment in (
        ("customer", "customer", None),
        ("caregiver", f"caregiver:{segment_id}", segment_id),
    ):
        cursor.execute(
            "INSERT INTO matching_schedule_recipient_snapshots "
            "(parent_snapshot_id,audience_type,recipient_key,segment_id,payload_snapshot,"
            "payload_fingerprint,delivery_status) VALUES (%s,%s,%s,%s,'{}',%s,'sent')",
            (snapshot_id, audience_type, recipient_key, recipient_segment, "f" * 64),
        )
        recipient_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO matching_schedule_confirmation_events "
            "(recipient_snapshot_id,confirmation_value,source,actor_id,reason,idempotency_key) "
            "VALUES (%s,'manually_confirmed','admin','test','durable fixture',%s)",
            (recipient_id, f"{case_no}-{recipient_key}-confirmed"),
        )


def _seed_settled_deposit(cursor, case_no) -> None:
    identity = f"{case_no}-deposit"
    cursor.execute(
        "INSERT INTO client_obligation_events (obligation_identity,case_no,obligation_type,direction,event_type,"
        "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,"
        "expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit',"
        "'receivable_from_client','established',0,2400,NULL,%s,%s,0,%s,'test','fixture')",
        (identity, case_no, date(2026, 7, 20), f"{identity}-source", f"{identity}-idem"),
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_obligations (obligation_identity,case_no,obligation_type,direction,amount_due_ntd,"
        "due_date,status,current_event_id,projection_version) VALUES (%s,%s,'deposit',"
        "'receivable_from_client',0,%s,'settled',%s,1)",
        (identity, case_no, date(2026, 7, 20), event_id),
    )
    cursor.execute(
        "INSERT INTO client_ledger_entries (case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,"
        "idempotency_key,actor,reason) VALUES (%s,'receipt',2400,%s,%s,%s,'test','fixture')",
        (case_no, date(2026, 7, 19), f"{identity}-receipt", f"{identity}-ledger-idem"),
    )
    ledger_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_ledger_obligation_allocations (ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
        "VALUES (%s,%s,2400,1)",
        (ledger_id, identity),
    )
    cursor.execute(
        "INSERT INTO client_deposit_settlement_projection (case_no,deposit_obligation_identity,settlement_state,"
        "contracted_amount_ntd,allocated_net_amount_ntd,settlement_identity,source_fingerprint,"
        "projection_version,latest_ledger_entry_id) VALUES (%s,%s,'settled',2400,2400,%s,%s,1,%s)",
        (case_no, identity, "b" * 64, "c" * 64, ledger_id),
    )


def test_assignment_plan_durable_job_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from api.routes.assignment_plan import (
        AssignmentPlanApplyBody,
        AssignmentPlanSegmentInput,
        apply_assignment_plan,
    )
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers
    from subsystems.jobs.command_application import DurableJobCommandApplication
    from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanPreviewRequest

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        body = AssignmentPlanApplyBody(
            segments=(AssignmentPlanSegmentInput(
                staff_id=staff_id,
                assigned_start_date=date(2026, 8, 1),
                assigned_end_date=date(2026, 8, 2),
                official_service_dates=(date(2026, 8, 1), date(2026, 8, 2)),
            ),),
            expected_order_version=0,
            expected_scheduling_version=0,
            expected_client_finance_version=0,
            expected_payroll_version=0,
            preview_fingerprint="0" * 64,
            reason="durable worker e2e",
        )
        preview = build_assignment_plan_application(connection).preview(
            AssignmentPlanPreviewRequest("AP-DURABLE-1", body.to_intent(), CorrelationId("preview"))
        )
        body = body.model_copy(update={"preview_fingerprint": preview.fingerprint.value})
        repository = BackgroundJobRepository(connection)
        job_application = DurableJobCommandApplication(repository, connection)
        apply_kwargs = {
            "body": body, "case_no": "AP-DURABLE-1", "idempotency_key": "durable-apply",
            "correlation_id": "durable-apply", "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": job_application,
        }
        apply_assignment_plan(**apply_kwargs)
        response = apply_assignment_plan(**apply_kwargs)
        job_id = response.data.job_id
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM background_jobs")
            assert cursor.fetchone() == {"count": 1}
        connection.begin()
        assert repository.claim_next_canonical_command("crashed-worker", 60) is not None
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE job_id=%s", (job_id,))
        connection.commit()
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(worker_connection), worker_connection, default_job_handlers(), "durable-test-worker", retry_delay_seconds=0)
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded", stored.error_payload
        assert stored.attempt_count == 2
        assert stored.result_reference == "assignment_plan:AP-DURABLE-1"
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM assignment_plan_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()
