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
EXISTING_DATABASE_ACCEPTANCE = os.getenv(
    "LABOR_UNION_EXISTING_DB_ACCEPTANCE"
) == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE and not EXISTING_DATABASE_ACCEPTANCE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


class _RollbackOnlyConnection:
    """Exercise real MySQL paths while preventing scenario commits from persisting."""

    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def begin(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return None


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
    arguments = dict(
        expected_order_version=facts.order_version,
        expected_scheduling_version=facts.scheduling_version,
        preview_fingerprint=preview.candidate.fingerprint.value,
        actor="test",
        reason="confirm restarted dates",
        idempotency_key=f"{case_no}-dates",
    )
    receipt = workflow.apply(
        case_no, dates, **arguments
    )
    replay = workflow.apply(
        case_no, dates, **arguments
    )
    assert replay == receipt
    return receipt


def _arrange_restarted_dates(connection, case_no: str, staff_id: int):
    from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.historical_restart_arrangement import (
        ArrangementSegmentIntent, HistoricalRestartArrangementWorkflow,
    )

    workflow = HistoricalRestartArrangementWorkflow(
        MySqlServiceDateConfirmationRepository(connection),
        lambda: MySqlUnitOfWork(connection),
    )
    segments = (ArrangementSegmentIntent(
        staff_id, (date(2026, 9, 3), date(2026, 9, 4)),
    ),)
    preview = workflow.preview(case_no, segments)
    receipt = workflow.apply(
        case_no, segments,
        expected_order_version=preview.order_version,
        expected_scheduling_version=preview.candidate.expected_aggregate_version,
        expected_confirmed_version=preview.confirmed_version,
        preview_fingerprint=preview.fingerprint.value,
        idempotency_key=f"{case_no}-arrangement",
        actor="test", reason="confirmed historical arrangement",
        correlation_id=f"{case_no}-arrangement",
    )
    assert workflow.apply(
        case_no, segments,
        expected_order_version=preview.order_version,
        expected_scheduling_version=preview.candidate.expected_aggregate_version,
        expected_confirmed_version=preview.confirmed_version,
        preview_fingerprint=preview.fingerprint.value,
        idempotency_key=f"{case_no}-arrangement",
        actor="test", reason="confirmed historical arrangement",
        correlation_id=f"{case_no}-arrangement",
    ) == receipt
    return receipt


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


def _confirm_actual_start(connection, case_no: str):
    from api.dependencies.order_actual_start import ActualStartApplication
    from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartWorkflow

    repository = MySqlOrderActualStartRepository(connection)
    workflow = ActualStartWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 9, 3, 12, tzinfo=TAIPEI_TIME_ZONE)),
    )
    application = ActualStartApplication(repository, workflow)
    preview = application.preview(case_no, date(2026, 9, 3))
    return application.apply(ActualStartApplyRequest(
        case_no,
        date(2026, 9, 3),
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        preview.fingerprint,
        IdempotencyKey(f"{case_no}-actual-start"),
        ActorContext("test"),
        "confirm restarted actual start",
        CorrelationId(f"{case_no}-actual-start"),
    ))


@pytest.mark.skipif(
    not EXISTING_DATABASE_ACCEPTANCE,
    reason="requires explicit existing-database acceptance opt-in",
)
@pytest.mark.parametrize("historical_status", ["歷史訂單－未服務", "歷史訂單－服務中"])
def test_existing_database_restart_writes_and_reads_canonical_schedule(
    historical_status: str,
) -> None:
    from infrastructure.mysql.leave_substitution_repository import (
        MySqlLeaveSubstitutionRepository,
    )
    from infrastructure.mysql.scheduling_current_projection_repository import (
        MySqlSchedulingCurrentProjectionRepository,
    )
    from infrastructure.mysql.weekly_operations_report_query_adapter import (
        MySqlWeeklyOperationsReportQueryAdapter,
    )
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery
    from subsystems.scheduling.current_projection_workflow import (
        SchedulingCurrentProjectionWorkflow,
        SchedulingCurrentQuery,
    )

    database = os.environ["DB_DATABASE"]
    case_no = (
        "CODEX-PR-A-20260903"
        if historical_status.endswith("未服務")
        else "CODEX-PR-B-20260903"
    )
    raw_connection = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    connection = _RollbackOnlyConnection(raw_connection)
    try:
        raw_connection.begin()
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            assert cursor.fetchone()["database_name"] == "union_db"
            cursor.execute("SELECT COUNT(*) AS count FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["count"] == 0
            staff_id, _legacy_assignment_id = _seed_owner_roots(
                cursor, case_no, historical_status
            )
            _seed_settled_deposit(cursor, case_no)

        report = MySqlWeeklyOperationsReportQueryAdapter(connection)
        assert report.list_service_facts(date(2026, 9, 3), date(2026, 9, 4)) == []
        restart = _restart(connection, case_no)
        dates = _confirm_dates(connection, case_no)
        assert dates.scheduling_version == restart.scheduling_version
        arrangement = _arrange_restarted_dates(connection, case_no, staff_id)
        assert arrangement.scheduling_version == restart.scheduling_version + 1

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment.id FROM scheduling_aggregates aggregate "
                "JOIN case_staff_assignments assignment "
                "ON assignment.generation_id=aggregate.effective_generation_id "
                "WHERE aggregate.case_no=%s AND assignment.status='planned'",
                (case_no,),
            )
            assignment_id = cursor.fetchone()["id"]
            cursor.execute(
                "SELECT work_date FROM staff_schedule WHERE assignment_id=%s "
                "AND effective_marker=1 AND is_work_day=1 ORDER BY work_date",
                (assignment_id,),
            )
            assert [row["work_date"] for row in cursor.fetchall()] == [
                date(2026, 9, 3), date(2026, 9, 4),
            ]
            cursor.execute(
                "SELECT policy_version,policy_kind,hourly_rate_ntd,source_identity_status "
                "FROM assignment_payroll_rate_snapshots WHERE assignment_id=%s",
                (assignment_id,),
            )
            assert cursor.fetchone() == {
                "policy_version": "approved-rates-v1",
                "policy_kind": "citizen",
                "hourly_rate_ntd": 300,
                "source_identity_status": "case-policy",
            }

        current = SchedulingCurrentProjectionWorkflow(
            MySqlSchedulingCurrentProjectionRepository(connection),
            FixedBusinessClock(datetime(2026, 9, 3, 12, tzinfo=TAIPEI_TIME_ZONE)),
        ).query(SchedulingCurrentQuery(staff_id, date(2026, 9, 3), date(2026, 9, 4)))
        assert [item.assignment_id for item in current.assignments] == [assignment_id]
        leave = MySqlLeaveSubstitutionRepository(connection).list_effective_assignments(case_no)
        assert [item["id"] for item in leave] == [assignment_id]
        assert [day["work_date"] for day in leave[0]["official_schedules"]] == [
            date(2026, 9, 3), date(2026, 9, 4),
        ]
        weekly = WeeklyOperationsReportQuery(
            report,
            lambda: datetime(2026, 9, 4, 18, tzinfo=TAIPEI_TIME_ZONE),
        ).query(date(2026, 9, 3), date(2026, 9, 4))
        assert [
            (row.case_no, row.weekly_work_days, row.weekly_hours)
            for row in weekly.service_rows
        ] == [(case_no, 2, 16)]
        actual_start = _confirm_actual_start(connection, case_no)
        assert actual_start.official_service_day_count == 2
    finally:
        raw_connection.rollback()
        raw_connection.close()


@pytest.mark.parametrize("historical_status", ["歷史訂單－未服務", "歷史訂單－服務中"])
def test_historical_restart_reenters_canonical_scheduling_and_weekly_report(
    historical_status: str,
) -> None:
    suffix = "unserved" if historical_status == "歷史訂單－未服務" else "in_service"
    database = f"{DATABASE}_{suffix}"
    bootstrap(_arguments(database))
    from infrastructure.mysql.scheduling_current_projection_repository import (
        MySqlSchedulingCurrentProjectionRepository,
    )
    from infrastructure.mysql.leave_substitution_repository import (
        MySqlLeaveSubstitutionRepository,
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
            staff_id, _legacy_assignment_id = _seed_owner_roots(cursor, case_no, historical_status)
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
        assert dates.scheduling_version == restart.scheduling_version
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s AND effective_marker=1", (case_no,))
            assert cursor.fetchone()["count"] == 0
        arrangement = _arrange_restarted_dates(connection, case_no, staff_id)
        assert arrangement.scheduling_version == restart.scheduling_version + 1
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment.id,assignment.generation_id FROM scheduling_aggregates aggregate "
                "JOIN case_staff_assignments assignment "
                "ON assignment.generation_id=aggregate.effective_generation_id "
                "WHERE aggregate.case_no=%s AND assignment.status='planned'",
                (case_no,),
            )
            saved_assignment = cursor.fetchone()
            assert saved_assignment is not None
            cursor.execute(
                "SELECT work_date,is_work_day,effective_marker FROM staff_schedule "
                "WHERE assignment_id=%s ORDER BY work_date",
                (saved_assignment["id"],),
            )
            assert cursor.fetchall() == [
                {"work_date": date(2026, 9, 3), "is_work_day": 1, "effective_marker": 1},
                {"work_date": date(2026, 9, 4), "is_work_day": 1, "effective_marker": 1},
            ]

        # The ordinary Scheduling read model must see the persisted generation
        # immediately; an HTTP success or React draft is not the acceptance oracle.
        saved_current = SchedulingCurrentProjectionWorkflow(
            MySqlSchedulingCurrentProjectionRepository(connection),
            FixedBusinessClock(datetime(2026, 9, 3, 12, tzinfo=TAIPEI_TIME_ZONE)),
        ).query(SchedulingCurrentQuery(staff_id, date(2026, 9, 3), date(2026, 9, 4)))
        assert len(saved_current.assignments) == 1
        assert saved_current.assignments[0].assignment_id == saved_assignment["id"]
        assert [
            (day.calendar_date, tuple(entry.occupancy_kind.value for entry in day.entries))
            for day in saved_current.days
        ] == [
            (date(2026, 9, 3), ("official_workday",)),
            (date(2026, 9, 4), ("official_workday",)),
        ]
        leave_assignments = MySqlLeaveSubstitutionRepository(
            connection
        ).list_effective_assignments(case_no)
        assert len(leave_assignments) == 1
        assert leave_assignments[0]["id"] == saved_assignment["id"]
        assert [item["work_date"] for item in leave_assignments[0]["official_schedules"]] == [
            date(2026, 9, 3), date(2026, 9, 4),
        ]
        saved_weekly = WeeklyOperationsReportQuery(
            report,
            lambda: datetime(2026, 9, 4, 18, tzinfo=TAIPEI_TIME_ZONE),
        ).query(date(2026, 9, 3), date(2026, 9, 4))
        assert [(row.case_no, row.weekly_work_days, row.weekly_hours) for row in saved_weekly.service_rows] == [
            (case_no, 2, 16),
        ]
        service = saved_weekly.service_rows[0]
        assert service.staff_name == f"{case_no} staff"
        assert service.service_start_date == date(2026, 9, 3)
        assert service.service_end_date == date(2026, 9, 4)

        # Before the canonical schedule existed this command failed with
        # scheduling_assignments_required.  Restart provenance itself must not
        # remain a blocker; the ordinary Actual Start writer still enforces
        # settlement, service lock, versions, and all downstream impacts.
        actual_start = _confirm_actual_start(connection, case_no)
        assert actual_start.official_service_day_count == 2
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT actual_start_date FROM orders WHERE case_no=%s", (case_no,)
            )
            assert cursor.fetchone()["actual_start_date"] == date(2026, 9, 3)
    finally:
        connection.close()


def test_three_segment_actual_start_carries_rates_and_rolls_back_on_failure(
    monkeypatch,
) -> None:
    """A real replacement keeps three owners and has one atomic failure boundary."""
    from api.dependencies.order_actual_start import ActualStartApplication
    from infrastructure.mysql import order_actual_start_repository as repository_module
    from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
    from infrastructure.mysql.scheduling_current_projection_repository import (
        MySqlSchedulingCurrentProjectionRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartWorkflow
    from subsystems.scheduling.current_projection_workflow import (
        SchedulingCurrentProjectionWorkflow, SchedulingCurrentQuery,
    )

    database = f"{DATABASE}_three_segment"
    bootstrap(_arguments(database))
    case_no = "HIST-THREE-SEGMENTS"
    connection = _connection_factory(database)()
    try:
        with connection.cursor() as cursor:
            first_staff_id, _ = _seed_owner_roots(cursor, case_no, "歷史訂單－服務中")
            _seed_settled_deposit(cursor, case_no)
            cursor.execute(
                "UPDATE clients SET service_type='週休2日' WHERE id=(SELECT client_id FROM orders WHERE case_no=%s)",
                (case_no,),
            )
            cursor.execute(
                "UPDATE orders SET status='服務中',service_days=3,end_date='2026-09-05',"
                "actual_end_date='2026-09-05' "
                "WHERE case_no=%s", (case_no,),
            )
            cursor.execute(
                "UPDATE confirmed_service_date_versions SET service_day_count=3 WHERE case_no=%s",
                (case_no,),
            )
            cursor.execute(
                "SELECT id FROM confirmed_service_date_versions WHERE case_no=%s", (case_no,),
            )
            confirmed_id = int(cursor.fetchone()["id"])
            cursor.execute(
                "INSERT INTO confirmed_service_date_days(confirmed_version_id,ordinal,service_date) "
                "VALUES (%s,3,'2026-09-05')", (confirmed_id,),
            )
            staff_ids = [first_staff_id]
            for ordinal in (2, 3):
                cursor.execute(
                    "INSERT INTO staff(name,phone,status) VALUES (%s,'0900000000','active')",
                    (f"{case_no} staff {ordinal}",),
                )
                staff_ids.append(int(cursor.lastrowid))
            cursor.execute(
                "INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,"
                "status,effective_marker,created_by,change_reason) "
                "VALUES (%s,1,1,'effective',1,'test','three-segment fixture')",
                (case_no,),
            )
            generation_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE scheduling_aggregates SET aggregate_version=1,generation_counter=1,"
                "effective_generation_id=%s WHERE case_no=%s", (generation_id, case_no),
            )
            source_assignment_ids = []
            for ordinal, (staff_id, rate) in enumerate(zip(staff_ids, (300, 350, 400)), 1):
                work_date = date(2026, 9, ordinal + 2)
                cursor.execute(
                    "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,"
                    "assignment_sequence,assigned_start_date,assigned_end_date,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'planned')",
                    (case_no, generation_id, f"{case_no}:g1:a{ordinal}", staff_id,
                     ordinal, work_date, work_date),
                )
                assignment_id = int(cursor.lastrowid)
                source_assignment_ids.append(assignment_id)
                cursor.execute(
                    "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,work_date,"
                    "is_work_day,is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,0,1)",
                    (case_no, staff_id, assignment_id, generation_id, work_date),
                )
                cursor.execute(
                    "INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,generation_id,"
                    "assignment_id,occupancy_type) VALUES (%s,%s,%s,%s,'assignment_interval')",
                    (staff_id, work_date, generation_id, assignment_id),
                )
                cursor.execute(
                    "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,"
                    "policy_kind,hourly_rate_ntd,source_identity_status) "
                    "VALUES (%s,'approved-rates-v1','citizen',%s,'case-policy')",
                    (assignment_id, rate),
                )
        connection.commit()

        def persisted_state():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lifecycle_version,actual_start_date,actual_end_date,status "
                    "FROM orders WHERE case_no=%s", (case_no,),
                )
                order = cursor.fetchone()
                cursor.execute(
                    "SELECT aggregate_version,generation_counter,effective_generation_id "
                    "FROM scheduling_aggregates WHERE case_no=%s", (case_no,),
                )
                scheduling = cursor.fetchone()
                counts = []
                for table in (
                    "scheduling_generations", "case_staff_assignments", "staff_schedule",
                    "order_actual_start_events", "order_actual_start_apply_receipts",
                ):
                    cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE case_no=%s", (case_no,))
                    counts.append(int(cursor.fetchone()["count"]))
                cursor.execute(
                    "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s",
                    (case_no,),
                )
                payroll_version = int(cursor.fetchone()["aggregate_version"])
                return order, scheduling, tuple(counts), payroll_version

        repository = MySqlOrderActualStartRepository(connection)
        workflow = ActualStartWorkflow(
            repository,
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026, 9, 10, 12, tzinfo=TAIPEI_TIME_ZONE)),
        )
        application = ActualStartApplication(repository, workflow)
        new_start = date(2026, 9, 6)  # Sunday: occupancy begins before the first workday.
        before = persisted_state()
        preview = application.preview(case_no, new_start)
        assert persisted_state() == before  # Preview has no persisted effect.
        assert [
            (item.staff_id, item.assigned_start_date, item.assigned_end_date,
             item.service_dates)
            for item in preview.scheduling.assignments
        ] == [
            (staff_ids[0], date(2026, 9, 6), date(2026, 9, 7), (date(2026, 9, 7),)),
            (staff_ids[1], date(2026, 9, 8), date(2026, 9, 8), (date(2026, 9, 8),)),
            (staff_ids[2], date(2026, 9, 9), date(2026, 9, 9), (date(2026, 9, 9),)),
        ]

        def apply_request(key: str, current_preview):
            return ActualStartApplyRequest(
                case_no, new_start,
                ExpectedVersion(current_preview.order_version),
                ExpectedVersion(current_preview.scheduling_version),
                current_preview.fingerprint, IdempotencyKey(f"{case_no}-{key}"),
                ActorContext("test"), "three-segment correction", CorrelationId(f"{case_no}-{key}"),
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM assignment_payroll_rate_snapshots WHERE assignment_id=%s",
                (source_assignment_ids[1],),
            )
        connection.commit()
        missing_source_state = persisted_state()
        with pytest.raises(ValueError, match="actual_start_rate_snapshot_missing_or_ambiguous"):
            application.preview(case_no, new_start)
        with pytest.raises(ValueError, match="actual_start_rate_snapshot_missing_or_ambiguous"):
            application.apply(apply_request("missing-source", preview))
        assert persisted_state() == missing_source_state
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,"
                "policy_kind,hourly_rate_ntd,source_identity_status) "
                "VALUES (%s,'approved-rates-v1','citizen',350,'case-policy')",
                (source_assignment_ids[1],),
            )
        connection.commit()
        assert persisted_state() == before

        def fail_after_scheduling_writer(*_args):
            raise RuntimeError("injected_rate_snapshot_persistence_failure")

        with monkeypatch.context() as patcher:
            patcher.setattr(
                repository_module, "persist_actual_start_rate_snapshot_carry",
                fail_after_scheduling_writer,
            )
            with pytest.raises(RuntimeError, match="injected_rate_snapshot_persistence_failure"):
                application.apply(apply_request("injected-failure", preview))
        assert persisted_state() == before  # The generation writer was rolled back too.

        current_preview = application.preview(case_no, new_start)
        application.apply(apply_request("success", current_preview))
        after = persisted_state()
        assert after[0]["actual_start_date"] == new_start
        assert after[0]["actual_end_date"] == date(2026, 9, 9)
        assert after[1]["aggregate_version"] == before[1]["aggregate_version"] + 1
        assert after[3] == before[3]  # No Payroll root mutation.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment.id,assignment.staff_id,assignment.assignment_sequence,"
                "assignment.assigned_start_date,assignment.assigned_end_date,"
                "snapshot.policy_version,snapshot.policy_kind,snapshot.hourly_rate_ntd,"
                "snapshot.source_identity_status "
                "FROM case_staff_assignments assignment "
                "JOIN assignment_payroll_rate_snapshots snapshot ON snapshot.assignment_id=assignment.id "
                "WHERE assignment.generation_id=%s ORDER BY assignment.assignment_sequence",
                (after[1]["effective_generation_id"],),
            )
            successor_rows = cursor.fetchall()
        assert [
            (row["staff_id"], row["assigned_start_date"], row["assigned_end_date"],
             row["policy_version"], row["policy_kind"], row["hourly_rate_ntd"],
             row["source_identity_status"])
            for row in successor_rows
        ] == [
            (staff_ids[0], date(2026, 9, 6), date(2026, 9, 7),
             "approved-rates-v1", "citizen", 300, f"carried-from:{source_assignment_ids[0]}"),
            (staff_ids[1], date(2026, 9, 8), date(2026, 9, 8),
             "approved-rates-v1", "citizen", 350, f"carried-from:{source_assignment_ids[1]}"),
            (staff_ids[2], date(2026, 9, 9), date(2026, 9, 9),
             "approved-rates-v1", "citizen", 400, f"carried-from:{source_assignment_ids[2]}"),
        ]
        calendar = SchedulingCurrentProjectionWorkflow(
            MySqlSchedulingCurrentProjectionRepository(connection),
            FixedBusinessClock(datetime(2026, 9, 10, 12, tzinfo=TAIPEI_TIME_ZONE)),
        )
        for staff_id, row, expected_date in zip(
            staff_ids, successor_rows, (date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9)),
        ):
            current = calendar.query(SchedulingCurrentQuery(
                staff_id, date(2026, 9, 6), date(2026, 9, 10),
            ))
            assert [item.assignment_id for item in current.assignments] == [row["id"]]
            assert [
                (day.calendar_date, entry.assignment_id)
                for day in current.days for entry in day.entries
                if entry.occupancy_kind.value == "official_workday"
            ] == [(expected_date, row["id"])]

        # The saved replacement is itself a valid source for another correction.
        later_start = date(2026, 9, 8)
        later_preview = application.preview(case_no, later_start)
        application.apply(ActualStartApplyRequest(
            case_no, later_start,
            ExpectedVersion(later_preview.order_version),
            ExpectedVersion(later_preview.scheduling_version),
            later_preview.fingerprint, IdempotencyKey(f"{case_no}-second-correction"),
            ActorContext("test"), "second three-segment correction",
            CorrelationId(f"{case_no}-second-correction"),
        ))
        second = persisted_state()
        assert second[0]["actual_start_date"] == later_start
        assert second[0]["actual_end_date"] == date(2026, 9, 10)
        assert second[1]["aggregate_version"] == after[1]["aggregate_version"] + 1
        assert second[3] == before[3]
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment.staff_id,assignment.assigned_start_date,"
                "assignment.assigned_end_date,snapshot.hourly_rate_ntd,"
                "snapshot.source_identity_status "
                "FROM case_staff_assignments assignment "
                "JOIN assignment_payroll_rate_snapshots snapshot ON snapshot.assignment_id=assignment.id "
                "WHERE assignment.generation_id=%s ORDER BY assignment.assignment_sequence",
                (second[1]["effective_generation_id"],),
            )
            second_rows = cursor.fetchall()
        assert [
            (row["staff_id"], row["assigned_start_date"], row["assigned_end_date"],
             row["hourly_rate_ntd"], row["source_identity_status"])
            for row in second_rows
        ] == [
            (staff_id, service_date, service_date, rate,
             f"carried-from:{source['id']}")
            for staff_id, service_date, rate, source in zip(
                staff_ids,
                (date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)),
                (300, 350, 400), successor_rows,
            )
        ]
    finally:
        connection.rollback()
        connection.close()


def test_actual_start_preserves_approved_substitution_and_leave_occupancy_mysql(
    monkeypatch,
) -> None:
    from api.dependencies.order_actual_start import ActualStartApplication
    from infrastructure.mysql import order_actual_start_repository as repository_module
    from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartWorkflow

    database = f"{DATABASE}_leave_replan"
    bootstrap(_arguments(database))
    case_no = "ACTUAL-START-LEAVE-SUBSTITUTE"
    connection = _connection_factory(database)()
    try:
        with connection.cursor() as cursor:
            caregiver, _ = _seed_owner_roots(cursor, case_no, "歷史訂單－服務中")
            _seed_settled_deposit(cursor, case_no)
            cursor.execute(
                "INSERT INTO staff(name,phone,status) VALUES (%s,'0900000001','active')",
                (f"{case_no} substitute",),
            )
            substitute = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE orders SET status='服務中',actual_start_date='2026-09-08',"
                "actual_end_date='2026-09-10',lifecycle_version=2 WHERE case_no=%s",
                (case_no,),
            )
            cursor.execute(
                "INSERT INTO holidays(holiday_date,holiday_name,is_double_pay_default) "
                "VALUES ('2026-09-07','fixture holiday',0)"
            )
            cursor.execute(
                "INSERT INTO scheduling_generations(case_no,generation_number,"
                "resulting_aggregate_version,status,effective_marker,created_by,"
                "change_reason,cancelled_at) "
                "VALUES (%s,1,1,'cancelled',NULL,'test','source before leave',CURRENT_TIMESTAMP)",
                (case_no,),
            )
            old_generation = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,"
                "assignment_sequence,assigned_start_date,assigned_end_date,status) "
                "VALUES (%s,%s,%s,%s,1,'2026-09-08','2026-09-09','replaced')",
                (case_no, old_generation, f"{case_no}:g1:a1", caregiver),
            )
            old_assignment = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,"
                "work_date,is_work_day,is_double_pay,effective_marker) "
                "VALUES (%s,%s,%s,%s,'2026-09-08',1,0,NULL)",
                (case_no, caregiver, old_assignment, old_generation),
            )
            old_schedule = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO scheduling_generations(case_no,generation_number,"
                "resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
                "VALUES (%s,2,2,'effective',1,'test','approved substitution')",
                (case_no,),
            )
            current_generation = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE scheduling_aggregates SET aggregate_version=2,generation_counter=2,"
                "effective_generation_id=%s WHERE case_no=%s",
                (current_generation, case_no),
            )
            current_assignments = []
            for ordinal, (staff_id, start_day, end_day, work_day) in enumerate((
                (caregiver, date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 9)),
                (substitute, date(2026, 9, 10), date(2026, 9, 10), date(2026, 9, 10)),
            ), 1):
                cursor.execute(
                    "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,"
                    "staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'planned')",
                    (case_no, current_generation, f"{case_no}:g2:a{ordinal}",
                     staff_id, ordinal, start_day, end_day),
                )
                assignment_id = int(cursor.lastrowid)
                current_assignments.append(assignment_id)
                cursor.execute(
                    "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,"
                    "work_date,is_work_day,is_double_pay,effective_marker) "
                    "VALUES (%s,%s,%s,%s,%s,1,0,1)",
                    (case_no, staff_id, assignment_id, current_generation, work_day),
                )
                cursor.execute(
                    "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,"
                    "policy_kind,hourly_rate_ntd,source_identity_status) "
                    "VALUES (%s,'approved-rates-v1','citizen',300,'case-policy')",
                    (assignment_id,),
                )
                for offset in range((end_day - start_day).days + 1):
                    cursor.execute(
                        "INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,"
                        "generation_id,assignment_id,occupancy_type) "
                        "VALUES (%s,%s,%s,%s,'assignment_interval')",
                        (staff_id, start_day.fromordinal(start_day.toordinal() + offset),
                         current_generation, assignment_id),
                    )
            batch_key = f"{case_no}-approved-leave"
            cursor.execute(
                "INSERT INTO scheduling_leave_substitution_batches(batch_key,case_no,"
                "original_assignment_id,command_fingerprint,preview_fingerprint,"
                "request_fingerprint,item_count,actor,reason,request_snapshot,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,1,'test','approved fixture','{}',%s)",
                (batch_key, case_no, old_assignment, 'a' * 64, 'b' * 64,
                 'c' * 64, f"{case_no}-leave-correlation"),
            )
            cursor.execute(
                "INSERT INTO scheduling_leave_substitution_outcomes(batch_key,item_index,"
                "event_key,original_assignment_id,original_schedule_id,original_staff_id,"
                "original_work_date,resolution_type,leave_occupancy_date,"
                "resulting_assignment_id,resulting_staff_id,resulting_service_date,"
                "result_fingerprint,outcome_snapshot) "
                "VALUES (%s,1,%s,%s,%s,%s,'2026-09-08','substitute','2026-09-08',"
                "%s,%s,'2026-09-10',%s,'{}')",
                (batch_key, f"{batch_key}-outcome", old_assignment, old_schedule,
                 caregiver, current_assignments[1], substitute, 'd' * 64),
            )
            outcome_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO scheduling_leave_occupancy_days(batch_key,item_index,"
                "outcome_id,generation_id,staff_id,occupancy_date,status,active_marker) "
                "VALUES (%s,1,%s,%s,%s,'2026-09-08','active',1)",
                (batch_key, outcome_id, current_generation, caregiver),
            )
            occupancy_id = int(cursor.lastrowid)
        connection.commit()

        repository = MySqlOrderActualStartRepository(connection)
        application = ActualStartApplication(repository, ActualStartWorkflow(
            repository, lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026, 9, 10, 12, tzinfo=TAIPEI_TIME_ZONE)),
        ))

        def state():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT actual_start_date,actual_end_date,lifecycle_version FROM orders "
                    "WHERE case_no=%s", (case_no,),
                )
                order = cursor.fetchone()
                cursor.execute(
                    "SELECT aggregate_version,effective_generation_id FROM scheduling_aggregates "
                    "WHERE case_no=%s", (case_no,),
                )
                scheduling = cursor.fetchone()
                cursor.execute(
                    "SELECT generation_id,status,active_marker,outcome_id FROM "
                    "scheduling_leave_occupancy_days WHERE id=%s", (occupancy_id,),
                )
                leave = cursor.fetchone()
                cursor.execute(
                    "SELECT original_staff_id,original_work_date,resulting_staff_id,"
                    "resulting_service_date FROM scheduling_leave_substitution_outcomes "
                    "WHERE id=%s", (outcome_id,),
                )
                outcome = cursor.fetchone()
                cursor.execute(
                    "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s",
                    (case_no,),
                )
                payroll_version = cursor.fetchone()["aggregate_version"]
                return order, scheduling, leave, outcome, payroll_version

        def request(preview, start_date, key):
            return ActualStartApplyRequest(
                case_no, start_date,
                ExpectedVersion(preview.order_version),
                ExpectedVersion(preview.scheduling_version),
                preview.fingerprint, IdempotencyKey(f"{case_no}-{key}"),
                ActorContext("test"), "leave-preserving correction",
                CorrelationId(f"{case_no}-{key}"),
            )

        before = state()
        with pytest.raises(ValueError, match="actual_start_leave_outcome_conflict"):
            application.preview(case_no, date(2026, 9, 6))
        assert state() == before
        first_preview = application.preview(case_no, date(2026, 9, 7))
        assert [item.service_dates for item in first_preview.scheduling.assignments] == [
            (date(2026, 9, 9),), (date(2026, 9, 10),),
        ]
        assert state() == before

        def fail_after_scheduling_writer(*_args):
            raise RuntimeError("injected_leave_preservation_rollback")

        with monkeypatch.context() as patcher:
            patcher.setattr(
                repository_module, "persist_actual_start_rate_snapshot_carry",
                fail_after_scheduling_writer,
            )
            with pytest.raises(RuntimeError, match="injected_leave_preservation_rollback"):
                application.apply(request(first_preview, date(2026, 9, 7), "failed"))
        assert state() == before

        application.apply(request(application.preview(case_no, date(2026, 9, 7)),
                                  date(2026, 9, 7), "first"))
        after = state()
        assert after[0]["actual_start_date"] == date(2026, 9, 7)
        assert after[1]["effective_generation_id"] != current_generation
        assert after[2]["generation_id"] == after[1]["effective_generation_id"]
        assert after[2]["status"] == "active" and after[2]["active_marker"] == 1
        assert after[3:] == before[3:]

        second_preview = application.preview(case_no, date(2026, 9, 8))
        application.apply(request(second_preview, date(2026, 9, 8), "second"))
        second = state()
        assert second[0]["actual_start_date"] == date(2026, 9, 8)
        assert second[2]["generation_id"] == second[1]["effective_generation_id"]
        assert second[2]["status"] == "active" and second[2]["active_marker"] == 1
        assert second[3:] == before[3:]
    finally:
        connection.rollback()
        connection.close()
