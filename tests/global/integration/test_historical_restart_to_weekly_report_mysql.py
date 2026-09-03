"""Cross-domain acceptance for historical restart into canonical Scheduling."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime
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


def _seed_owner_roots(cursor, case_no: str, lifecycle_status: str) -> tuple[int, int]:
    cursor.execute(
        "INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) "
        "VALUES (%s,%s,'一般市民','新竹市','東區','09:00-17:00','連續服務')",
        (case_no, f"{case_no} client"),
    )
    client_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO staff(name,phone,status) VALUES (%s,'0900000000','active')",
        (f"{case_no} staff",),
    )
    staff_id = int(cursor.lastrowid)
    cursor.execute("INSERT INTO staff_regions(staff_id,region_name) VALUES (%s,'新竹市')", (staff_id,))
    cursor.execute(
        "INSERT INTO staff_matching_preference_profiles(staff_id,version,created_by,updated_by) "
        "VALUES (%s,1,'test','test')",
        (staff_id,),
    )
    cursor.execute(
        "SELECT id,preference_key FROM staff_matching_preference_definitions "
        "WHERE preference_key IN ('preferred_service_days','daily_service_hours')"
    )
    definitions = {row["preference_key"]: int(row["id"]) for row in cursor.fetchall()}
    service_days_definition = definitions["preferred_service_days"]
    daily_hours_definition = definitions["daily_service_hours"]
    cursor.executemany(
        "INSERT INTO staff_matching_preference_values(staff_id,definition_id,value_json,profile_version,updated_by) "
        "VALUES (%s,%s,%s,1,'test')",
        [
            (staff_id, service_days_definition, '{"minimum":1,"maximum":30}'),
            (staff_id, daily_hours_definition, '{"values":[8]}'),
        ],
    )
    cursor.execute(
        "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
        "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,service_end_time,"
        "service_end_day_offset,staff_payment_due_date,actual_start_date) "
        "VALUES (%s,%s,%s,1,'2026-09-03','2026-09-04',2,8,0,0,'09:00:00','17:00:00',0,"
        "'2026-09-18',%s)",
        (case_no, client_id, lifecycle_status,
         date(2026, 9, 3) if lifecycle_status == "歷史訂單－服務中" else None),
    )
    cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
    cursor.execute("INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
    cursor.execute("INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter) VALUES (%s,0,0)", (case_no,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events(case_no,policy_version,client_hourly_rate_ntd,"
        "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,'terms-v1',300,1,'2026-09-01','2026-09-03','2026-09-04',0,%s,%s,'test','fixture')",
        (case_no, f"{case_no}-terms-source", f"{case_no}-terms-key"),
    )
    terms_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_payment_terms(case_no,policy_version,client_hourly_rate_ntd,"
        "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES (%s,'terms-v1',300,1,'2026-09-01','2026-09-03','2026-09-04',%s)",
        (case_no, terms_event_id),
    )
    digest = hashlib.sha256(case_no.encode()).hexdigest()
    cursor.execute(
        "INSERT INTO case_architecture_bootstrap_events(case_no,order_version,client_payment_terms_event_id,"
        "client_policy_version,client_hourly_rate_ntd,payroll_policy_version,payroll_policy_kind,"
        "payroll_hourly_rate_ntd,source_identity_status,candidate_fingerprint,idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,1,%s,'terms-v1',300,'approved-rates-v1','citizen',300,'一般市民',%s,%s,'test','fixture',%s)",
        (case_no, terms_event_id, digest, f"{case_no}-bootstrap", f"{case_no}-bootstrap-correlation"),
    )
    bootstrap_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO case_payroll_rate_policy_snapshots(case_no,policy_version,policy_kind,hourly_rate_ntd,"
        "source_identity_status,source_event_id) VALUES (%s,'approved-rates-v1','citizen',300,'一般市民',%s)",
        (case_no, bootstrap_event_id),
    )
    cursor.execute(
        "INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) "
        "VALUES (%s,%s,'contract_completed','test','fixture',%s)",
        (case_no, f"{case_no}-contract", f"{case_no}-contract-key"),
    )
    cursor.execute(
        "INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,after_status,actor,"
        "business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'historical_order_adoption','洽談中',%s,'test','2026-09-03',0,%s,'{}')",
        (case_no, lifecycle_status, f"{case_no}-adoption-lifecycle"),
    )
    lifecycle_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status,"
        "assigned_start_date,assigned_end_date) VALUES (%s,%s,1,'completed','2026-09-03','2026-09-04')",
        (case_no, staff_id),
    )
    legacy_assignment_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO historical_order_adoption_receipts(idempotency_key,command_fingerprint,source_event_identity,"
        "source_fingerprint,preview_fingerprint,case_no,outcome,expected_version,resulting_version,lifecycle_event_id,"
        "assignment_count,result_snapshot,actor,reason,correlation_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,'adopted',0,1,%s,1,'{}','test','fixture',%s)",
        (f"{case_no}-adoption", digest, f"{case_no}-source", digest, digest, case_no,
         lifecycle_event_id, f"{case_no}-adoption-correlation"),
    )
    receipt_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO historical_order_pairing_evidence(receipt_id,caregiver_ordinal,staff_name,staff_id,resolution,"
        "source_start_date,source_end_date,assignment_id,issue_codes) "
        "VALUES (%s,1,%s,%s,'assignment_candidate','2026-09-03','2026-09-04',%s,'[]')",
        (receipt_id, f"{case_no} staff", staff_id, legacy_assignment_id),
    )
    cursor.execute(
        "INSERT INTO confirmed_service_date_versions(case_no,version,order_version,scheduling_version,"
        "service_day_count,service_date_fingerprint,is_current,confirmed_by_actor_id,reason) "
        "VALUES (%s,1,1,0,2,%s,1,'test','historical fixture')",
        (case_no, digest),
    )
    confirmed_id = int(cursor.lastrowid)
    cursor.executemany(
        "INSERT INTO confirmed_service_date_days(confirmed_version_id,ordinal,service_date) VALUES (%s,%s,%s)",
        [(confirmed_id, 1, date(2026, 9, 3)), (confirmed_id, 2, date(2026, 9, 4))],
    )
    return staff_id, legacy_assignment_id


def _seed_settled_deposit(cursor, case_no: str) -> None:
    identity = f"{case_no}-deposit"
    cursor.execute(
        "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,"
        "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,"
        "expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit','receivable_from_client',"
        "'established',0,2400,NULL,'2026-09-01',%s,0,%s,'test','fixture')",
        (identity, case_no, f"{identity}-source", f"{identity}-event"),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,"
        "due_date,status,current_event_id,projection_version) VALUES (%s,%s,'deposit','receivable_from_client',"
        "0,'2026-09-01','settled',%s,1)", (identity, case_no, event_id),
    )
    cursor.execute(
        "INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,"
        "idempotency_key,actor,reason) VALUES (%s,'receipt',2400,'2026-09-01',%s,%s,'test','fixture')",
        (case_no, f"{identity}-receipt", f"{identity}-ledger"),
    )
    ledger_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
        "VALUES (%s,%s,2400,1)", (ledger_id, identity),
    )
    cursor.execute(
        "INSERT INTO client_deposit_settlement_projection(case_no,deposit_obligation_identity,settlement_state,"
        "contracted_amount_ntd,allocated_net_amount_ntd,settlement_identity,source_fingerprint,projection_version,"
        "latest_ledger_entry_id) VALUES (%s,%s,'settled',2400,2400,%s,%s,1,%s)",
        (
            case_no,
            identity,
            hashlib.sha256(f"{identity}-settlement".encode()).hexdigest(),
            hashlib.sha256(identity.encode()).hexdigest(),
            ledger_id,
        ),
    )


def _connection_factory(database: str):
    def connect():
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

    return connect


def _create_matching_plan(connection, database: str, case_no: str, staff_id: int) -> tuple[int, int]:
    from infrastructure.mysql.segmented_availability_repository import MySqlSegmentedAvailabilityFactsRepository
    from subsystems.scheduling import matching_plan_workflow

    connect = _connection_factory(database)

    matching_plan_workflow.get_connection = connect
    result = matching_plan_workflow.create_matching_plan_version(
        case_no,
        [{"staff_id": staff_id, "start_date": "2026-09-03", "end_date": "2026-09-04"}],
        "test",
        "2026-09-03",
        facts_port=MySqlSegmentedAvailabilityFactsRepository(connect),
    )
    plan_id = int(result["plan_id"])
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id FROM caregiver_matching_plan_segments WHERE plan_id=%s AND segment_order=1",
        (plan_id,),
    )
    segment_id = int(cursor.fetchone()["id"])
    cursor.close()
    return plan_id, segment_id


def _record_matching_acceptance(database: str, case_no: str, plan_id: int, segment_id: int) -> None:
    from datetime import timezone

    from domains.scheduling.matching_communication import (
        CaregiverWillingness,
        CustomerMatchingDecision,
        MatchingPlanReference,
    )
    from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.line.capabilities import LineCapability
    from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
    from subsystems.scheduling.matching_notification_contracts import RecordManualMatchingResponseCommand

    connect = _connection_factory(database)
    application = MatchingNotificationApplication(
        lambda: ManagedLineMySqlUnitOfWork(connect()),
        lambda: datetime(2026, 9, 3, 12, tzinfo=timezone.utc),
        availability_validator=lambda _state: None,
    )
    actor = ActorContext("test", (LineCapability.MATCHING_OVERRIDE.value,))
    plan = MatchingPlanReference(case_no, plan_id, 0)
    application.record_manual_response(RecordManualMatchingResponseCommand(
        plan, segment_id, CaregiverWillingness.WILLING, None,
        "acceptance caregiver confirmation", actor, ExpectedVersion(0),
        IdempotencyKey(f"{case_no}-caregiver-willing"),
        CorrelationId(f"{case_no}-caregiver-willing"),
    ))
    application.record_manual_response(RecordManualMatchingResponseCommand(
        MatchingPlanReference(case_no, plan_id, 1), None, None, CustomerMatchingDecision.ACCEPTED,
        "acceptance customer confirmation", actor, ExpectedVersion(1),
        IdempotencyKey(f"{case_no}-customer-accepted"),
        CorrelationId(f"{case_no}-customer-accepted"),
    ))


def _establish_commitment_and_lock(
    database: str,
    archive_root,
    case_no: str,
    plan_id: int,
    segment_id: int,
) -> None:
    from infrastructure.archive.contract_documents import (
        archive_contract_document,
        discard_uncommitted_contract_document,
    )
    from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
    from infrastructure.mysql.order_terms_read_model import load_contract_client_finance_facts, select_order
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.contract_signing.staff_contract_application import (
        ManualStaffContractAttestationCommand,
        StaffContractSigningApplication,
    )
    from subsystems.scheduling import availability_lock_acquisition_workflow

    connect = _connection_factory(database)
    application = StaffContractSigningApplication(
        connect,
        archive_root=archive_root,
        now=lambda: datetime(2026, 9, 3, 12),
        archive_document=archive_contract_document,
        discard_document=discard_uncommitted_contract_document,
        order_selector=select_order,
        finance_facts_loader=load_contract_client_finance_facts,
        finance_terms_writer=persist_client_finance_terms_impact,
    )
    preview = application.preview_manual_attestation(
        case_no=case_no,
        matching_segment_id=segment_id,
        confirmation_method="phone",
        reason="acceptance signed contract",
    )
    receipt = application.record_manual_attestation(ManualStaffContractAttestationCommand(
        case_no, segment_id, b"signed-contract", "signed.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "phone", "acceptance signed contract", str(preview["preview_fingerprint"]), "test",
        IdempotencyKey(f"{case_no}-staff-contract"),
        CorrelationId(f"{case_no}-staff-contract"),
    ))
    assert receipt.commitment_id is not None

    availability_lock_acquisition_workflow.get_connection = connect
    lock_preview = availability_lock_acquisition_workflow.preview_caregiver_availability_lock(
        case_no, plan_id,
    )
    assert lock_preview["apply_allowed"] is True
    lock = availability_lock_acquisition_workflow.acquire_caregiver_availability_lock(
        case_no,
        plan_id,
        f"{case_no}-availability-lock",
        "test",
        lock_preview["preview_fingerprint"],
    )
    assert lock["result"] == "created"


def _restart(connection, case_no: str):
    from domains.orders.historical_precision_restart import HistoricalPrecisionRestartIntent
    from infrastructure.mysql.historical_precision_restart_repository import MySqlHistoricalPrecisionRestartRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.orders.historical_precision_restart_workflow import (
        ApplyHistoricalPrecisionRestart, HistoricalPrecisionRestartWorkflow,
    )

    workflow = HistoricalPrecisionRestartWorkflow(
        MySqlHistoricalPrecisionRestartRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        lambda: datetime(2026, 9, 3, 12),
    )
    intent = HistoricalPrecisionRestartIntent(case_no)
    preview = workflow.preview(intent)
    facts = preview.domain.facts
    return workflow.apply(ApplyHistoricalPrecisionRestart(
        intent, facts.order_version, facts.scheduling_version, facts.historical_day_revision,
        facts.confirmed_service_date_version, PreviewFingerprint(preview.fingerprint.value),
        IdempotencyKey(f"{case_no}-restart"), ActorContext("test"), "restart acceptance",
        CorrelationId(f"{case_no}-restart-correlation"),
    ))


def _confirm_dates(connection, case_no: str):
    from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
    from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow

    workflow = ServiceDateConfirmationWorkflow(
        MySqlServiceDateConfirmationRepository(connection), lambda: MySqlUnitOfWork(connection),
        MySqlMatchingScheduleConfirmationRepository(connection),
    )
    dates = (date(2026, 9, 3), date(2026, 9, 4))
    preview = workflow.preview(case_no, dates)
    facts = workflow.query(case_no)
    return workflow.apply(
        case_no, dates, expected_order_version=facts.order_version,
        expected_scheduling_version=facts.scheduling_version,
        preview_fingerprint=preview.candidate.fingerprint.value, actor="test",
        reason="confirm restarted dates", idempotency_key=f"{case_no}-dates",
    )


def _confirm_matching(connection, case_no: str, plan_id: int) -> None:
    from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.matching_schedule_confirmation import MatchingScheduleConfirmationWorkflow

    workflow = MatchingScheduleConfirmationWorkflow(
        MySqlMatchingScheduleConfirmationRepository(connection), lambda: MySqlUnitOfWork(connection)
    )
    preview = workflow.preview_manual(case_no, plan_id)
    state = workflow.prepare_manual(
        case_no, plan_id, "test", "acceptance confirmation",
        preview["confirmed_service_date_version"], preview["preview_fingerprint"], f"{case_no}-manual",
    )
    for recipient in state["recipients"]:
        workflow.confirm(
            recipient["recipient_snapshot_id"], "manually_confirmed", "test",
            "acceptance confirmation", f"{case_no}-confirm-{recipient['recipient_snapshot_id']}",
        )
    assert workflow.query(case_no, plan_id)["gate_passed"] is True


def _apply_assignment(connection, case_no: str, staff_id: int):
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanApplyRequest, AssignmentPlanPreviewRequest

    intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(
        staff_id, date(2026, 9, 3), date(2026, 9, 4),
        (date(2026, 9, 3), date(2026, 9, 4)),
    ),))
    app = build_assignment_plan_application(connection)
    try:
        preview = app.preview(AssignmentPlanPreviewRequest(case_no, intent, CorrelationId(f"{case_no}-preview")))
    except Exception as error:
        typed = getattr(error, "error", None)
        blockers = getattr(typed, "domain_blockers", ())
        raise AssertionError(f"assignment plan preview blocked: {blockers}") from error
    return app.apply(AssignmentPlanApplyRequest(
        case_no, intent, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version),
        preview.fingerprint, IdempotencyKey(f"{case_no}-assignment"),
        ActorContext("test"), "canonical assignment acceptance", CorrelationId(f"{case_no}-apply"),
    ))


@pytest.mark.parametrize("historical_status", ["歷史訂單－未服務", "歷史訂單－服務中"])
def test_historical_restart_reenters_canonical_scheduling_and_weekly_report(
    historical_status: str,
    tmp_path,
) -> None:
    suffix = "unserved" if historical_status == "歷史訂單－未服務" else "in_service"
    database = f"{DATABASE}_{suffix}"
    bootstrap(_arguments(database))
    from infrastructure.mysql.scheduling_current_projection_repository import (
        MySqlSchedulingCurrentProjectionRepository,
    )
    from infrastructure.mysql.weekly_operations_report_query_adapter import (
        MySqlWeeklyOperationsReportQueryAdapter,
    )
    from infrastructure.mysql import weekly_operations_report_query_adapter
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery
    from subsystems.scheduling.current_projection_workflow import (
        SchedulingCurrentProjectionWorkflow,
        SchedulingCurrentQuery,
    )

    case_no = "HIST-UNSERVED" if historical_status.endswith("未服務") else "HIST-IN-SERVICE"
    connection = pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            staff_id, legacy_assignment_id = _seed_owner_roots(cursor, case_no, historical_status)
            _seed_settled_deposit(cursor, case_no)
        connection.commit()

        weekly_operations_report_query_adapter.get_connection = _connection_factory(database)
        report = MySqlWeeklyOperationsReportQueryAdapter(connection)
        assert report.list_service_facts(date(2026, 9, 3), date(2026, 9, 4)) == []

        restart = _restart(connection, case_no)
        assert restart.lifecycle_status == "訂單成立"
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["count"] == 0
            cursor.execute("SELECT is_current FROM confirmed_service_date_versions WHERE case_no=%s AND version=1", (case_no,))
            assert cursor.fetchone()["is_current"] is None
        assert report.list_service_facts(date(2026, 9, 3), date(2026, 9, 4)) == []

        dates = _confirm_dates(connection, case_no)
        assert dates.service_dates == (date(2026, 9, 3), date(2026, 9, 4))
        plan_id, segment_id = _create_matching_plan(connection, database, case_no, staff_id)
        _record_matching_acceptance(database, case_no, plan_id, segment_id)
        _confirm_matching(connection, case_no, plan_id)
        _establish_commitment_and_lock(
            database, tmp_path / suffix, case_no, plan_id, segment_id,
        )
        # The preceding normal-flow applications commit on their own request
        # connections. End this readback connection's repeatable-read snapshot
        # before composing the next request boundary.
        connection.rollback()
        assignment = _apply_assignment(connection, case_no, staff_id)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,generation_id,status FROM case_staff_assignments "
                "WHERE case_no=%s AND id<>%s AND generation_id IS NOT NULL", (case_no, legacy_assignment_id),
            )
            canonical = cursor.fetchone()
            assert canonical is not None
            cursor.execute(
                "SELECT work_date,is_work_day,effective_marker FROM staff_schedule "
                "WHERE assignment_id=%s ORDER BY work_date", (canonical["id"],),
            )
            assert cursor.fetchall() == [
                {"work_date": date(2026, 9, 3), "is_work_day": 1, "effective_marker": 1},
                {"work_date": date(2026, 9, 4), "is_work_day": 1, "effective_marker": 1},
            ]
            cursor.execute(
                "SELECT occupancy_date,occupancy_type FROM scheduling_effective_occupancy "
                "WHERE assignment_id=%s ORDER BY occupancy_date", (canonical["id"],),
            )
            occupancy = cursor.fetchall()
            assert [row for row in occupancy if row["occupancy_type"] == "assignment_interval"] == [
                {"occupancy_date": date(2026, 9, 3), "occupancy_type": "assignment_interval"},
                {"occupancy_date": date(2026, 9, 4), "occupancy_type": "assignment_interval"},
            ]
        current = SchedulingCurrentProjectionWorkflow(
            MySqlSchedulingCurrentProjectionRepository(connection),
            FixedBusinessClock(datetime(2026, 9, 3, 12, tzinfo=TAIPEI_TIME_ZONE)),
        ).query(SchedulingCurrentQuery(staff_id, date(2026, 9, 3), date(2026, 9, 4)))
        assert len(current.assignments) == 1
        assert current.assignments[0].case_no == case_no
        assert current.assignments[0].assignment_id == canonical["id"]
        assert [
            (day.calendar_date, tuple(entry.occupancy_kind.value for entry in day.entries))
            for day in current.days
        ] == [
            (date(2026, 9, 3), ("official_workday",)),
            (date(2026, 9, 4), ("official_workday",)),
        ]

        weekly = WeeklyOperationsReportQuery(
            report,
            lambda: datetime(2026, 9, 4, 18, tzinfo=TAIPEI_TIME_ZONE),
        ).query(date(2026, 9, 3), date(2026, 9, 4))
        assert len(weekly.service_rows) == 1
        service = weekly.service_rows[0]
        assert service.case_no == case_no
        assert service.staff_name == f"{case_no} staff"
        assert service.service_start_date == date(2026, 9, 3)
        assert service.service_end_date == date(2026, 9, 4)
        assert service.weekly_work_days == 2
        assert service.weekly_hours == 16
        assert assignment.scheduling_generation == restart.scheduling_generation + 1
    finally:
        connection.close()
