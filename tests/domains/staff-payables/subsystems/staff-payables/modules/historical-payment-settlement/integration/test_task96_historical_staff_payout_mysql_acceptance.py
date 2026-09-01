"""Task 96 real-MySQL acceptance for the Staff Payables historical payout owner flow."""

from __future__ import annotations

from datetime import date
import hashlib
import os
from uuid import uuid4

import pymysql
import pytest

from domains.staff_payables.historical_payout import (
    HistoricalStaffConfirmationKind,
    HistoricalStaffPayoutIntent,
    HistoricalStaffSourceAvailability,
)
from infrastructure.mysql.historical_staff_payout_repository import (
    HistoricalStaffPayoutMySqlUnitOfWork,
    MySqlHistoricalStaffPayoutRepository,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.staff_payables.historical_payment_settlement import (
    ApplyHistoricalStaffPayout,
    HistoricalStaffPayoutWorkflow,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE
    or not DATABASE.startswith("lu_test_")
    or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _seed_adopted_staff_case(connection, case_no: str) -> tuple[int, str]:
    staff_identity = f"S{uuid4().hex[:10].upper()}"
    obligation_identity = f"historical-staff-obligation:{case_no}"
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name) VALUES (%s,%s)",
            (case_no, "Task 96 MySQL historical client"),
        )
        cursor.execute(
            "INSERT INTO staff(name,identity_card,status) VALUES (%s,%s,'active')",
            ("Task 96 MySQL historical staff", staff_identity),
        )
        staff_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,staff_id,status) "
            "VALUES (%s,(SELECT id FROM clients WHERE case_no=%s),%s,'訂單完成')",
            (case_no, case_no, staff_id),
        )
        cursor.execute(
            "INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) "
            "VALUES (%s,%s,1,'completed')",
            (case_no, staff_id),
        )
        assignment_id = int(cursor.lastrowid)
        source_fingerprint = hashlib.sha256(case_no.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO historical_order_adoption_receipts("
            "idempotency_key,command_fingerprint,source_event_identity,source_fingerprint,"
            "preview_fingerprint,case_no,outcome,expected_version,resulting_version,"
            "lifecycle_event_id,assignment_count,result_snapshot,actor,reason,correlation_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,'adopted',0,0,NULL,1,%s,'task96-mysql',"
            "'adopted historical case for owner acceptance',%s)",
            (
                f"task96-adoption:{case_no}",
                source_fingerprint,
                f"task96-source:{case_no}",
                source_fingerprint,
                source_fingerprint,
                case_no,
                '{"source":"task96-mysql"}',
                f"task96-adoption-correlation:{case_no}",
            ),
        )
        adoption_receipt_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_payable_accounts(staff_id,aggregate_version) VALUES (%s,0)",
            (staff_id,),
        )
        payroll_fingerprint = hashlib.sha256(
            f"payroll:{case_no}".encode()
        ).hexdigest()
        cursor.execute(
            "INSERT INTO staff_obligation_events("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
            "event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,"
            "expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,2400,"
            "'2026-08-01',%s,0,1,%s,'task96-mysql','historical payout fixture')",
            (
                obligation_identity,
                assignment_id,
                case_no,
                staff_id,
                payroll_fingerprint,
                f"task96-obligation:{case_no}",
            ),
        )
        event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
            "amount_due_ntd,due_date,status,current_event_id,payroll_version) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',2400,'2026-08-01',"
            "'open',%s,1)",
            (obligation_identity, assignment_id, case_no, staff_id, event_id),
        )
    connection.commit()
    return staff_id, obligation_identity


def test_historical_staff_payout_mysql_query_preview_apply_replay_readback() -> None:
    case_no = f"T96-HSP-{uuid4().hex[:12].upper()}"
    connection = _connection()
    try:
        staff_id, obligation_identity = _seed_adopted_staff_case(connection, case_no)
        repository = MySqlHistoricalStaffPayoutRepository(connection)
        workflow = HistoricalStaffPayoutWorkflow(
            repository,
            lambda: HistoricalStaffPayoutMySqlUnitOfWork(connection),
        )
        intent = HistoricalStaffPayoutIntent(
            case_no,
            staff_id,
            HistoricalStaffConfirmationKind.PAID,
            (obligation_identity,),
            date(2026, 7, 31),
            None,
            HistoricalStaffSourceAvailability.UNRECOVERABLE,
            f"masked-evidence:{case_no}",
        )

        queried = workflow.query(case_no, staff_id)
        assert queried.adopted is True
        assert queried.normal_bank_candidate_identities == ()
        preview = workflow.preview(intent)
        assert preview.candidate.can_apply is True
        assert preview.candidate.amount_snapshot_ntd == 2400

        request = ApplyHistoricalStaffPayout(
            intent,
            ExpectedVersion(preview.candidate.staff_payables_version),
            preview.candidate.adoption_receipt_id,
            preview.candidate.fingerprint,
            IdempotencyKey(f"task96-historical-staff:{case_no}"),
            ActorContext("task96-mysql-acceptance"),
            "Confirm adopted historical staff payout.",
            CorrelationId(f"task96-historical-staff:{case_no}"),
        )
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt

        readback = workflow.readback(case_no, staff_id)
        assert readback.owner_terminal is True
        assert readback.facts.staff_payables_version == 1
        assert readback.projections[0].obligation_identity == obligation_identity
        assert readback.projections[0].amount_snapshot_ntd == 2400
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM historical_staff_payout_events "
                "WHERE case_no=%s",
                (case_no,),
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM historical_staff_payout_obligation_links "
                "WHERE obligation_identity=%s",
                (obligation_identity,),
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT id FROM historical_staff_payout_events WHERE event_identity=%s",
                (receipt.event_identity,),
            )
            event_id = int(cursor.fetchone()["id"])
            # Resolve the event by its immutable identity; the outbox remains pending
            # for the downstream projector and is still part of the committed owner UoW.
            cursor.execute(
                "SELECT event_id,status,attempt_count FROM historical_staff_payout_source_outbox "
                "WHERE event_id=%s",
                (event_id,),
            )
            outbox = cursor.fetchone()
            assert outbox is not None
            assert outbox["status"] == "pending"
            assert outbox["attempt_count"] == 0
    finally:
        connection.close()
