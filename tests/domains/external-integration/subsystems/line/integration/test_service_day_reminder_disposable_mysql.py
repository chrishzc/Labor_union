"""Native MySQL acceptance for service-day reminder lineage and stop gates."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, date, datetime
import os

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from infrastructure.mysql.line_repository_support import aware_utc


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)

_NOW = datetime(2026, 9, 20, 2, tzinfo=UTC)
_SERVICE_DATE = date(2026, 9, 18)
_RULE = {
    "rules": [
        {
            "id": "service-day-log-reminder",
            "event_code": "service_time_checkpoint",
            "recipient_selector": "assigned_caregiver",
            "template_id": "service-day-log-reminder",
            "enabled": True,
            "schedule": {"kind": "service_end"},
            "frequency": {"kind": "once"},
            "predicates": ["baby_log_missing"],
        }
    ]
}
_TEMPLATE = {
    "templates": [
        {
            "id": "service-day-log-reminder",
            "message_type": "text",
            "enabled": True,
            "content": "請補寶寶日誌",
            "variables": [],
        }
    ]
}


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


def _connection_factory(database: str):
    return lambda: _connect(database)


def _seed_configuration(connection) -> None:
    from domains.line.configuration import LineConfigurationKind
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from shared_kernel.identities import ActorContext, CorrelationId
    from subsystems.line.capabilities import LineCapability
    from subsystems.line.configuration_application import LineConfigurationApplication

    application = LineConfigurationApplication(lambda: LineMySqlUnitOfWork(connection))
    results = application.bootstrap_missing(
        {
            LineConfigurationKind.MESSAGE_TEMPLATES: _TEMPLATE,
            LineConfigurationKind.NOTIFICATION_RULES: _RULE,
        },
        ActorContext("issue-325-test", (LineCapability.CONFIG_MANAGE.value,)),
        reason="issue 325 disposable configuration",
        correlation_id=CorrelationId("issue-325-config"),
    )
    assert [result.snapshot.revision.value for result in results] == [1, 1]


def _seed_case(connection, *, case_no: str, line_user_id: str) -> tuple[int, int]:
    with connection.cursor() as cursor:
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
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
            "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,service_end_time,"
            "service_end_day_offset,staff_payment_due_date,actual_start_date) "
            "VALUES (%s,%s,'服務中',1,'2026-09-18','2026-09-18',1,8,0,0,'09:00:00','17:00:00',0,"
            "'2026-09-30','2026-09-18')",
            (case_no, client_id),
        )
        cursor.execute(
            "INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,"
            "effective_marker,created_by,change_reason) "
            "VALUES (%s,1,1,'effective',1,'issue-325-test','fixture')",
            (case_no,),
        )
        generation_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter,effective_generation_id) "
            "VALUES (%s,1,1,%s)",
            (case_no, generation_id),
        )
        cursor.execute(
            "INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
            "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
            "VALUES (%s,%s,%s,%s,1,'2026-09-18','2026-09-18',0,'active')",
            (case_no, generation_id, f"{case_no}:g1:a1", staff_id),
        )
        assignment_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,"
            "is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,'2026-09-18',1,0,1)",
            (case_no, staff_id, assignment_id, generation_id),
        )
        cursor.execute(
            "INSERT INTO line_platform_users(line_user_id,friend_status,aggregate_version) "
            "VALUES (%s,'active',1)",
            (line_user_id,),
        )
        cursor.execute(
            "INSERT INTO line_identity_role_bindings(line_user_id,subject_type,binding_status,"
            "subject_reference,aggregate_version) VALUES (%s,'staff','bound',%s,1)",
            (line_user_id, str(staff_id)),
        )
    connection.commit()
    return staff_id, assignment_id


def _lineage(connection) -> tuple[dict[str, object], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
            "source.id AS source_id,source.source_event_identity,decision.decision_status,decision.reason_code,"
            "decision.recipient_type,decision.recipient_identity,intent.id AS intent_id,"
            "intent.intent_status,intent.delivery_task_id,task.processing_status,task.error_code,task.scheduled_at_utc "
            "FROM line_notification_source_events source "
            "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
            "LEFT JOIN line_notification_intents intent ON intent.decision_id=decision.id "
            "LEFT JOIN line_delivery_tasks task ON task.id=intent.delivery_task_id "
            "WHERE source.event_code='service_time_checkpoint' ORDER BY source.id"
        )
        return tuple(cursor.fetchall())


def _counts(connection) -> tuple[int, int, int, int]:
    tables = (
        "line_notification_source_events",
        "line_notification_decisions",
        "line_notification_intents",
        "line_delivery_tasks",
    )
    with connection.cursor() as cursor:
        result = []
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            result.append(int(cursor.fetchone()["total"]))
    return tuple(result)


def _apply_non_cooking_log(connection, staff_id: int, assignment_id: int, line_user_id: str):
    from domains.scheduling.service_day_log import ServiceDayLogIntent
    from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.service_day_log_workflow import (
        ApplyServiceDayLog,
        PreviewServiceDayLog,
        ServiceDayLogApplication,
    )

    application = ServiceDayLogApplication(
        MySqlServiceDayLogRepository(connection),
        lambda: MySqlUnitOfWork(connection),
    )
    intent = ServiceDayLogIntent(_SERVICE_DATE, "寶寶今日狀況正常", ())
    preview_command = PreviewServiceDayLog(staff_id, line_user_id, assignment_id, intent)
    preview = application.preview(preview_command)
    assert preview.can_apply is True
    command = ApplyServiceDayLog(
        staff_id,
        line_user_id,
        assignment_id,
        intent,
        f"issue-325-log-{assignment_id}",
        preview.preview_fingerprint,
    )
    created = application.apply(command)
    replay = application.apply(command)
    assert created.outcome == "created"
    assert replay.outcome == "existing"
    assert replay.log_id == created.log_id
    return created


def _cancel_assignment_with_formal_rebuild(connection, case_no: str, assignment_id: int) -> None:
    from domains.scheduling.generation import SchedulingGenerationCandidate
    from infrastructure.mysql.scheduling_replacement_writer import persist_scheduling_replacement
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.fingerprints import fingerprint_payload
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.orders.terms_workflow import SchedulingReplacementCommand

    candidate = SchedulingGenerationCandidate(
        case_no,
        2,
        1,
        2,
        (assignment_id,),
        (),
        (),
    )
    preview_fingerprint = fingerprint_payload(
        {"case_no": case_no, "assignment_id": assignment_id, "operation": "cancel"}
    )
    command = SchedulingReplacementCommand(
        candidate,
        "orders_cancellation_rebuild",
        1,
        fingerprint_payload({"issue": 325, "case_no": case_no}),
        preview_fingerprint,
        IdempotencyKey(f"issue-325-rebuild-{case_no}"),
        ActorContext("issue-325-test"),
        "issue 325 rebuild invalidation",
        CorrelationId(f"issue-325-rebuild-{case_no}"),
    )
    with MySqlUnitOfWork(connection) as unit_of_work:
        with connection.cursor() as cursor:
            result = persist_scheduling_replacement(cursor, command)
        assert result.scheduling_version == 2
        unit_of_work.commit()


def test_service_day_reminder_native_mysql_lineage_stop_rebuild_and_replay() -> None:
    from domains.line.configuration import LineConfigurationKind
    from domains.line.identities import LineConfigurationRevision, LineDeliveryTaskId
    from infrastructure.mysql.line_configuration_publication_repository import (
        MySqlLineConfigurationRepository,
    )
    from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
    from infrastructure.mysql.line_notification_repository import (
        LineNotificationManualReplayValidationError,
    )
    from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
    from infrastructure.mysql.scheduling_checkpoint_notification_source_worker import (
        MySqlSchedulingCheckpointNotificationSourceWorker,
    )
    from infrastructure.mysql.scheduling_rebuild_notification_invalidation_worker import (
        MySqlSchedulingRebuildNotificationInvalidationWorker,
    )
    from infrastructure.mysql.service_day_checkpoint_worker import MySqlServiceDayCheckpointWorker
    from infrastructure.mysql.service_day_log_notification_stop_worker import (
        MySqlServiceDayLogNotificationStopWorker,
    )
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.line.capabilities import LineCapability
    from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery
    from subsystems.line.delivery_worker import LineDeliveryWorker
    from subsystems.line.notification_manual_replay_application import (
        LineNotificationManualReplayApplication,
    )

    database = f"{DATABASE}_service_day_reminder"
    bootstrap(_arguments(database))
    connect = _connection_factory(database)
    connection = connect()
    completion_case = "REMINDER-COMPLETE-325"
    rebuild_case = "REMINDER-REBUILD-325"
    try:
        _seed_configuration(connection)
        completion_staff, completion_assignment = _seed_case(
            connection,
            case_no=completion_case,
            line_user_id="U-issue-325-completion",
        )
        _rebuild_staff, rebuild_assignment = _seed_case(
            connection,
            case_no=rebuild_case,
            line_user_id="U-issue-325-rebuild",
        )

        configuration = MySqlLineConfigurationRepository(connection)
        templates = configuration.get(LineConfigurationKind.MESSAGE_TEMPLATES)
        rules = configuration.get(LineConfigurationKind.NOTIFICATION_RULES)
        assert templates.revision == LineConfigurationRevision(1)
        assert rules.revision == LineConfigurationRevision(1)
        assert "service-day-log-reminder" in templates.definition_json
        assert "service_time_checkpoint" in rules.definition_json
        assert "assigned_caregiver" in rules.definition_json

        assert MySqlServiceDayCheckpointWorker(connect, lambda: _NOW).run_once() == 2
        assert (
            MySqlSchedulingCheckpointNotificationSourceWorker(connect, lambda: _NOW).run_once()
            == 2
        )
        connection.rollback()
        lineage = _lineage(connection)
        assert _counts(connection) == (2, 2, 2, 2)
        assert {
            (
                row["case_no"],
                row["decision_status"],
                row["reason_code"],
                row["recipient_type"],
                row["recipient_identity"],
                row["intent_status"],
                row["processing_status"],
            )
            for row in lineage
        } == {
            (
                completion_case,
                "intent_created",
                "rule_matched",
                "user",
                "U-issue-325-completion",
                "scheduled",
                "pending",
            ),
            (
                rebuild_case,
                "intent_created",
                "rule_matched",
                "user",
                "U-issue-325-rebuild",
                "scheduled",
                "pending",
            ),
        }

        before_replay = _counts(connection)
        assert (
            MySqlSchedulingCheckpointNotificationSourceWorker(connect, lambda: _NOW).run_once()
            == 0
        )
        connection.rollback()
        assert _counts(connection) == before_replay

        completion_row = next(row for row in lineage if row["case_no"] == completion_case)
        rebuild_row = next(row for row in lineage if row["case_no"] == rebuild_case)
        _apply_non_cooking_log(
            connection,
            completion_staff,
            completion_assignment,
            "U-issue-325-completion",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM scheduling_service_day_log_outbox "
                "WHERE delivery_status='pending'"
            )
            assert int(cursor.fetchone()["total"]) == 1

        # MySQL owns event creation time; claim only when that persisted task is due.
        delivery_now = max(_NOW, aware_utc(completion_row["scheduled_at_utc"]))
        delivery_repository = MySqlLineDeliveryTaskRepository(connection)
        connection.begin()
        claimed = delivery_repository.claim_specific(
            LineDeliveryTaskId(int(completion_row["delivery_task_id"])),
            ClaimLineDeliveryTasksQuery("issue-325-delivery", delivery_now, 1),
        )
        connection.commit()
        assert claimed is not None
        assert claimed.status.value == "processing"

        provider_calls: list[object] = []

        class Provider:
            def send(self, request):
                provider_calls.append(request)
                raise AssertionError("cancelled reminder must not cross provider boundary")

        class InterleavedDeliveryWorker(LineDeliveryWorker):
            def __init__(self):
                super().__init__(
                    lambda: ManagedLineMySqlUnitOfWork(connect()),
                    Provider(),
                    "issue-325-delivery",
                    lambda: delivery_now,
                    batch_size=1,
                )
                self._claimed_once = False
                self._stopped = False

            def _claim(self):
                if self._claimed_once:
                    return ()
                self._claimed_once = True
                return (claimed,)

            def _manual_replay_validation_failure(self, task):
                if not self._stopped:
                    self._stopped = True
                    assert MySqlServiceDayLogNotificationStopWorker(
                        connect, lambda: _NOW
                    ).run_once() == 1
                return super()._manual_replay_validation_failure(task)

        assert InterleavedDeliveryWorker().run_once() == 1
        assert provider_calls == []
        connection.rollback()
        after_completion = _lineage(connection)
        completed = next(row for row in after_completion if row["case_no"] == completion_case)
        unaffected = next(row for row in after_completion if row["case_no"] == rebuild_case)
        assert (completed["intent_status"], completed["processing_status"], completed["error_code"]) == (
            "cancelled",
            "cancelled",
            "service_day_log_completed",
        )
        assert (unaffected["intent_status"], unaffected["processing_status"]) == (
            "scheduled",
            "pending",
        )

        actor = ActorContext("issue-325-test", (LineCapability.CONFIG_MANAGE.value,))
        manual_replay = LineNotificationManualReplayApplication(
            lambda: ManagedLineMySqlUnitOfWork(connect()),
            lambda: _NOW,
        )
        with pytest.raises(
            LineNotificationManualReplayValidationError,
            match="notification_source_not_currently_applicable",
        ):
            manual_replay.apply(
                int(completion_row["source_id"]),
                actor,
                "completion stale replay",
                IdempotencyKey("issue-325-completion-replay"),
                CorrelationId("issue-325-completion-replay"),
            )

        _cancel_assignment_with_formal_rebuild(
            connection,
            rebuild_case,
            rebuild_assignment,
        )
        assert MySqlSchedulingRebuildNotificationInvalidationWorker(
            connect, lambda: _NOW
        ).run_once() == 1
        connection.rollback()
        after_rebuild = _lineage(connection)
        rebuilt = next(row for row in after_rebuild if row["case_no"] == rebuild_case)
        assert (rebuilt["intent_status"], rebuilt["processing_status"], rebuilt["error_code"]) == (
            "cancelled",
            "cancelled",
            "assignment_replaced",
        )
        with pytest.raises(
            LineNotificationManualReplayValidationError,
            match="notification_source_not_currently_applicable",
        ):
            manual_replay.apply(
                int(rebuild_row["source_id"]),
                actor,
                "rebuild stale replay",
                IdempotencyKey("issue-325-rebuild-replay"),
                CorrelationId("issue-325-rebuild-replay"),
            )

        assert MySqlSchedulingRebuildNotificationInvalidationWorker(
            connect, lambda: _NOW
        ).run_once() == 0
        assert MySqlServiceDayLogNotificationStopWorker(connect, lambda: _NOW).run_once() == 0
        assert LineDeliveryWorker(
            lambda: ManagedLineMySqlUnitOfWork(connect()),
            Provider(),
            "issue-325-final-delivery",
            lambda: _NOW,
            batch_size=2,
        ).run_once() == 0
        assert provider_calls == []
    finally:
        connection.close()
