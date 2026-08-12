"""Real MySQL proof for the isolated Orders auto-completion transition."""

from __future__ import annotations

from datetime import datetime
import os
from uuid import uuid4

import pytest


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_auto_completion_enforces_time_and_version_then_replays_the_receipt():
    case_no = f"OAC-{uuid4().hex[:16]}"
    _seed_in_service_completion_roots(case_no)
    service, connection = _service()
    try:
        before = _snapshot(connection, case_no)
        _assert_early_completion_has_no_writes(service, case_no)
        assert _snapshot(connection, case_no) == before

        request = _request(case_no, 0, "complete", "2026-08-04T17:00:00+08:00")
        receipt = service.apply(request)
        assert service.apply(request) == receipt
        _assert_completed(connection, case_no)

        after = _snapshot(connection, case_no)
        _assert_stale_version_has_no_writes(service, case_no)
        assert _snapshot(connection, case_no) == after
    finally:
        connection.close()


def _service():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_auto_completion_repository import (
        MySqlOrderAutoCompletionRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.auto_completion_workflow import AutoCompleteOrderService

    connection = get_connection()
    return (
        AutoCompleteOrderService(
            MySqlOrderAutoCompletionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        ),
        connection,
    )


def _request(case_no: str, expected_version: int, suffix: str, evaluation_at: str):
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.auto_completion_workflow import AutoCompletionApplyRequest

    identity = f"order-auto-completion:{suffix}:{case_no}"
    return AutoCompletionApplyRequest(
        case_no,
        ExpectedVersion(expected_version),
        datetime.fromisoformat(evaluation_at),
        IdempotencyKey(identity),
        ActorContext("lu-test-order-auto-completion"),
        "service completion clock reached",
        CorrelationId(identity),
    )


def _assert_early_completion_has_no_writes(service, case_no: str) -> None:
    from subsystems.orders.auto_completion_workflow import AutoCompletionWorkflowError

    with pytest.raises(AutoCompletionWorkflowError) as error:
        service.apply(_request(case_no, 0, "early", "2026-08-04T16:59:00+08:00"))
    assert error.value.error.code == "auto_completion_time_not_reached"


def _assert_stale_version_has_no_writes(service, case_no: str) -> None:
    from subsystems.orders.auto_completion_workflow import AutoCompletionWorkflowError

    with pytest.raises(AutoCompletionWorkflowError) as error:
        service.apply(_request(case_no, 0, "stale", "2026-08-04T17:00:00+08:00"))
    assert error.value.error.code == "order_version_conflict"


def _seed_in_service_completion_roots(case_no: str) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    policy_version = f"auto-completion:{case_no}"
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,%s)", (case_no, "Synthetic Completion Client"))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES (%s,'active')", (f"Synthetic Completion Staff {case_no}",))
            staff_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orders("
                "case_no,client_id,status,lifecycle_version,start_date,service_days,"
                "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
                "service_end_day_offset,actual_start_date,actual_end_date,staff_payment_due_date) "
                "VALUES (%s,%s,'服務中',0,'2026-08-01',1,8,0,'09:00:00','17:00:00',"
                "0,'2026-08-01','2026-08-04','2026-08-15')",
                (case_no, client_id),
            )
            generation_id = _insert_scheduling_roots(cursor, case_no, staff_id)
            assignment_id = _insert_assignment_root(cursor, case_no, generation_id, staff_id)
            _insert_client_finance_roots(cursor, case_no, policy_version)
            _insert_payroll_roots(cursor, case_no, assignment_id, policy_version)
        connection.commit()
    finally:
        connection.close()


def _insert_scheduling_roots(cursor, case_no: str, staff_id: int) -> int:
    cursor.execute(
        "INSERT INTO scheduling_generations("
        "case_no,generation_number,resulting_aggregate_version,status,effective_marker,"
        "created_by,change_reason) VALUES (%s,1,1,'effective',1,'lu-test','fixture')",
        (case_no,),
    )
    generation_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO scheduling_aggregates("
        "case_no,aggregate_version,generation_counter,effective_generation_id) "
        "VALUES (%s,1,1,%s)",
        (case_no, generation_id),
    )
    return int(generation_id)


def _insert_assignment_root(cursor, case_no: str, generation_id: int, staff_id: int) -> int:
    cursor.execute(
        "INSERT INTO case_staff_assignments("
        "case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
        "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
        "VALUES (%s,%s,%s,%s,1,'2026-08-04','2026-08-04',0,'planned')",
        (case_no, generation_id, f"{case_no}:g1:a1", staff_id),
    )
    assignment_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO staff_schedule("
        "case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,"
        "is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,'2026-08-04',1,0,1)",
        (case_no, staff_id, assignment_id, generation_id),
    )
    return int(assignment_id)


def _insert_client_finance_roots(cursor, case_no: str, policy_version: str) -> None:
    cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events("
        "case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,%s,100,0,'2026-08-15','2026-08-20',NULL,0,%s,%s,'lu-test','fixture')",
        (case_no, policy_version, f"terms:{case_no}", f"terms:{case_no}"),
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_payment_terms("
        "case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES (%s,%s,100,0,'2026-08-15','2026-08-20',NULL,%s)",
        (case_no, policy_version, event_id),
    )


def _insert_payroll_roots(cursor, case_no: str, assignment_id: int, policy_version: str) -> None:
    cursor.execute("INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
    cursor.execute(
        "INSERT INTO payroll_rate_policies(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES (%s,'citizen',150,'2026-01-01')",
        (policy_version,),
    )
    cursor.execute(
        "INSERT INTO assignment_payroll_rate_snapshots("
        "assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
        "VALUES (%s,%s,'citizen',150,'fixture')",
        (assignment_id, policy_version),
    )


def _snapshot(connection, case_no: str) -> tuple[int, int, int, int]:
    with connection.cursor() as cursor:
        counts = []
        for table in (
            "application_command_claims",
            "order_auto_completion_apply_receipts",
            "order_lifecycle_state_events",
            "orders_domain_outbox",
        ):
            column = "aggregate_identity" if table == "application_command_claims" else "case_no"
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {column}=%s", (case_no,))
            counts.append(int(cursor.fetchone()["count"]))
    return tuple(counts)


def _assert_completed(connection, case_no: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT status,lifecycle_version FROM orders WHERE case_no=%s", (case_no,))
        assert cursor.fetchone() == {"status": "訂單完成", "lifecycle_version": 1}
    assert _snapshot(connection, case_no) == (1, 1, 1, 1)
