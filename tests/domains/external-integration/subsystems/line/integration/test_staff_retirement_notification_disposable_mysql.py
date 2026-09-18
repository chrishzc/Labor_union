"""Native MySQL acceptance for Staff retirement LINE effects and notification lineage."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import os

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)

_NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
_EFFECTIVE_AT = datetime(2026, 9, 18, 10, tzinfo=UTC)
_TEMPLATE = {
    "templates": [
        {
            "id": "LU96-M1-STAFF-RETIRE-CARD-V1",
            "message_type": "text",
            "enabled": True,
            "content": "月嫂退役通知",
            "variables": [],
        }
    ]
}
_RULE = {
    "rules": [
        {
            "id": "LU96-M1-STAFF-RETIRE-RULE-V1",
            "event_code": "staff.retirement.committed",
            "recipient_selector": "staff.binding_owner",
            "template_id": "LU96-M1-STAFF-RETIRE-CARD-V1",
            "enabled": True,
            "schedule": {"kind": "immediate"},
            "frequency": {"kind": "once"},
            "predicates": [],
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


def _seed_configuration(connection) -> None:
    from domains.line.configuration import LineConfigurationKind
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from shared_kernel.identities import ActorContext, CorrelationId
    from subsystems.line.capabilities import LineCapability
    from subsystems.line.configuration_application import LineConfigurationApplication

    results = LineConfigurationApplication(
        lambda: LineMySqlUnitOfWork(connection)
    ).bootstrap_missing(
        {
            LineConfigurationKind.MESSAGE_TEMPLATES: _TEMPLATE,
            LineConfigurationKind.NOTIFICATION_RULES: _RULE,
        },
        ActorContext("issue-313-test", (LineCapability.CONFIG_MANAGE.value,)),
        reason="issue 313 disposable configuration",
        correlation_id=CorrelationId("issue-313-config"),
    )
    assert [result.snapshot.revision.value for result in results] == [1, 1]


def _seed_staff(connection) -> tuple[int, str]:
    line_user_id = "U-issue-313-retired-staff"
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO staff(name,phone,status) VALUES "
            "('Issue 313 staff','0900000313','active')"
        )
        staff_id = int(cursor.lastrowid)
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
        cursor.execute(
            "INSERT INTO line_rich_menu_publication_tasks(menu_definition_id,"
            "configuration_revision,operation,publication_status,definition_snapshot,"
            "provider_menu_id,idempotency_key,correlation_id,requested_by_actor_id) "
            "VALUES ('default_menu',1,'publish','published',%s,'richmenu-default-313',"
            "'issue-313-default-menu','issue-313-default-menu','issue-313-test')",
            ('{"id":"default_menu"}',),
        )
    connection.commit()
    return staff_id, line_user_id


def _counts(connection) -> dict[str, int]:
    tables = (
        "staff_lifecycle_apply_receipts",
        "line_identity_revocation_requests",
        "line_domain_outbox",
        "line_notification_source_events",
        "line_notification_decisions",
        "line_notification_intents",
        "line_delivery_tasks",
    )
    result = {}
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            result[table] = int(cursor.fetchone()["total"])
    return result


def test_staff_retirement_projects_revocation_menu_and_notification_once() -> None:
    from domains.staff.retirement import StaffLifecycleTransition
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from infrastructure.mysql.staff_retirement_repository import MySqlStaffRetirementRepository
    from shared_kernel.clock import FixedBusinessClock
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.line.staff_retirement_effect import LineStaffRetirementEffect
    from subsystems.staff.retirement_workflow import StaffLifecycleApplyRequest, StaffLifecycleWorkflow

    database = f"{DATABASE}_staff_retirement_notification"
    bootstrap(_arguments(database))
    connection = _connect(database)
    try:
        _seed_configuration(connection)
        staff_id, line_user_id = _seed_staff(connection)
        workflow = StaffLifecycleWorkflow(
            MySqlStaffRetirementRepository(connection),
            lambda: LineMySqlUnitOfWork(connection),
            FixedBusinessClock(_NOW),
            LineStaffRetirementEffect(),
        )
        preview = workflow.preview(
            staff_id,
            StaffLifecycleTransition.RETIRE,
            _EFFECTIVE_AT,
            "left_union",
        )
        request = StaffLifecycleApplyRequest(
            staff_id,
            StaffLifecycleTransition.RETIRE,
            _EFFECTIVE_AT,
            "left_union",
            ExpectedVersion(0),
            preview.fingerprint,
            IdempotencyKey(f"issue-313-staff-retirement:{staff_id}:1"),
            ActorContext("admin:313"),
            CorrelationId(f"issue-313-staff-retirement:{staff_id}:1"),
        )

        created = workflow.apply(request)
        counts = _counts(connection)
        replay = workflow.apply(request)

        assert created == replay
        assert _counts(connection) == counts
        assert set(counts.values()) == {1}

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT lifecycle_state,aggregate_version FROM staff_lifecycle_states "
                "WHERE staff_id=%s",
                (staff_id,),
            )
            assert cursor.fetchone() == {
                "lifecycle_state": "retired",
                "aggregate_version": 1,
            }
            cursor.execute(
                "SELECT binding_status,aggregate_version FROM line_identity_role_bindings "
                "WHERE line_user_id=%s AND subject_type='staff'",
                (line_user_id,),
            )
            assert cursor.fetchone() == {
                "binding_status": "revocation_pending",
                "aggregate_version": 2,
            }
            cursor.execute(
                "SELECT request_status,provider_menu_id FROM line_identity_revocation_requests"
            )
            assert cursor.fetchone() == {
                "request_status": "pending_menu_reset",
                "provider_menu_id": "richmenu-default-313",
            }
            cursor.execute(
                "SELECT intent_type,processing_status FROM line_domain_outbox"
            )
            assert cursor.fetchone() == {
                "intent_type": "line.identity.revocation.menu_reset",
                "processing_status": "pending",
            }
            cursor.execute(
                "SELECT source.source_event_identity,source.event_code,source.source_domain,"
                "source.source_aggregate_identity,source.source_version,decision.decision_status,"
                "decision.rule_id,decision.recipient_identity,intent.intent_status,"
                "task.processing_status FROM line_notification_source_events source "
                "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
                "JOIN line_notification_intents intent ON intent.decision_id=decision.id "
                "JOIN line_delivery_tasks task ON task.id=intent.delivery_task_id"
            )
            assert cursor.fetchone() == {
                "source_event_identity": f"staff-retirement:{staff_id}:1",
                "event_code": "staff.retirement.committed",
                "source_domain": "staff",
                "source_aggregate_identity": str(staff_id),
                "source_version": 1,
                "decision_status": "intent_created",
                "rule_id": "LU96-M1-STAFF-RETIRE-RULE-V1",
                "recipient_identity": line_user_id,
                "intent_status": "scheduled",
                "processing_status": "pending",
            }
    finally:
        connection.close()
