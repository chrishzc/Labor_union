"""
File: test_line_mysql_repositories.py
Description: 驗證 LINE MySQL adapters 的交易、cleanup claim、owner 邊界與資料形狀契約。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pymysql.err import IntegrityError

from domains.line.identities import (
    LineDeliveryTaskId,
    LineGroupId,
    LineConfigurationRevision,
    LineRichMenuPublicationId,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityClaim
from domains.line.webhook import LineWebhookProcessingStatus
from domains.line.rich_menu import LineRichMenuPublicationStatus
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityRepository,
)
from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
)
from infrastructure.mysql.line_configuration_publication_repository import (
    MySqlLineRichMenuPublicationRepository,
)
from infrastructure.mysql.line_media_order_group_repository import (
    MySqlLineOrderGroupBindingRepository,
)
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from infrastructure.mysql.line_webhook_inbox_repository import (
    MySqlLineWebhookInboxRepository,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery
from subsystems.line.delivery_admin_contracts import LineDeliveryAdminQuery
from subsystems.line.webhook_contracts import ClaimLineWebhookEventsQuery
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    LineOrderGroupCommandOutcome,
)
from subsystems.line.rich_menu_contracts import (
    ClaimLineRichMenuPublicationsQuery,
    LineRichMenuPublicationQuery,
    QueueLineRichMenuPublicationCommand,
)
from subsystems.line.ports import (
    LineRichMenuCleanupWorkItem,
    LineRichMenuPublicationStep,
    LineRichMenuStepAttemptEvent,
    LineRichMenuStepAttemptOutcome,
)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class ScriptedCursor:
    def __init__(self, *, one_rows=(), all_rows=()) -> None:
        self.one_rows = list(one_rows)
        self.all_rows = list(all_rows)
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, parameters=()):
        normalized = tuple(parameters)
        assert sql.count("%s") == len(normalized)
        self.executed.append((sql, normalized))

    def fetchone(self):
        return self.one_rows.pop(0) if self.one_rows else None

    def fetchall(self):
        return self.all_rows.pop(0) if self.all_rows else ()


class FakeConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self):
        return self.cursor_instance


class TransactionConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__(ScriptedCursor())
        self.actions: list[str] = []

    def begin(self):
        self.actions.append("begin")

    def commit(self):
        self.actions.append("commit")

    def rollback(self):
        self.actions.append("rollback")


def test_order_group_numbered_queries_use_count_limit_and_offset() -> None:
    cursor = ScriptedCursor(
        one_rows=({"total": 26}, {"total": 11}),
        all_rows=(
            ({
                "case_no": "CASE-26",
                "group_id": None,
                "binding_status": "active",
                "aggregate_version": 3,
            },),
            ({
                "event_id": 11,
                "case_no": "CASE-26",
                "event_type": "group_activated",
                "actor_id": "admin:7",
                "occurred_at_utc": NOW,
                "invitation_fingerprint": None,
            },),
        ),
    )
    repository = MySqlLineOrderGroupBindingRepository(FakeConnection(cursor))

    groups = repository.list_numbered(status="active", page=2, page_size=25)
    events = repository.events_numbered("CASE-26", page=2, page_size=10)

    assert (groups.page, groups.page_size, groups.total, groups.total_pages) == (2, 25, 26, 2)
    assert groups.items[0].case_no == "CASE-26"
    assert (events.page, events.page_size, events.total, events.total_pages) == (2, 10, 11, 2)
    assert events.items[0].event_id == 11
    assert "LIMIT %s OFFSET %s" in cursor.executed[1][0]
    assert cursor.executed[1][1] == ("active", 25, 25)
    assert cursor.executed[3][1] == ("CASE-26", "CASE-26", 10, 10)


class DuplicateAttemptCursor(ScriptedCursor):
    def execute(self, sql, parameters=()):
        if sql.startswith("INSERT INTO line_rich_menu_publication_step_attempt_events"):
            raise IntegrityError(1062, "duplicate attempt event")
        return super().execute(sql, parameters)


class LostClaimCursor(ScriptedCursor):
    def execute(self, sql, parameters=()):
        super().execute(sql, parameters)
        if sql.startswith("UPDATE line_rich_menu_publication_tasks"):
            self.rowcount = 0


def _webhook_row(status: str, version: int) -> dict[str, object]:
    return {
        "event_identity": "event-1",
        "destination_id": "destination-1",
        "event_type": "message",
        "source_type": "user",
        "source_identity": "U-user",
        "source_user_id": "U-user",
        "occurred_at_utc": NOW.replace(tzinfo=None),
        "payload_fingerprint": "a" * 64,
        "payload_snapshot": {"type": "message"},
        "identity_source": "provider",
        "is_redelivery": 0,
        "processing_status": status,
        "aggregate_version": version,
    }


def test_webhook_transition_binds_every_sql_parameter() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            _webhook_row("pending", 0),
            _webhook_row("processing", 1),
        )
    )
    repository = MySqlLineWebhookInboxRepository(FakeConnection(cursor))

    snapshot = repository.transition(
        LineWebhookEventId("event-1"),
        ExpectedVersion(0),
        LineWebhookProcessingStatus.PROCESSING,
    )

    assert snapshot.status is LineWebhookProcessingStatus.PROCESSING
    update_parameters = cursor.executed[1][1]
    assert update_parameters[:2] == ("processing", "processing")


def test_delivery_claim_binds_all_three_clock_predicates() -> None:
    cursor = ScriptedCursor(all_rows=((),))
    repository = MySqlLineDeliveryTaskRepository(FakeConnection(cursor))

    claimed = repository.claim(ClaimLineDeliveryTasksQuery("worker-1", NOW, 10))

    assert claimed == ()
    parameters = cursor.executed[0][1]
    assert parameters[0] == parameters[1] == parameters[2]
    assert parameters[3] == 10


def _delivery_admin_row(*, missing: str | None = None, extra: bool = False) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 7,
        "recipient_type": "user",
        "recipient_identity": "U-secret",
        "message_kind": "text",
        "payload_snapshot": '{"text":"secret"}',
        "processing_status": "sent",
        "scheduled_at_utc": NOW.replace(tzinfo=None),
        "source_aggregate_type": "customer_service_ticket",
        "source_aggregate_identity": "CASE-secret",
        "completed_attempts": 1,
        "max_attempts": 3,
        "next_attempt_at_utc": None,
        "provider_message_id": "provider-secret",
        "error_code": None,
        "error_message": None,
        "sent_at_utc": NOW.replace(tzinfo=None),
        "failed_at_utc": None,
        "created_at_utc": NOW.replace(tzinfo=None),
        "updated_at_utc": NOW.replace(tzinfo=None),
    }
    if missing is not None:
        row.pop(missing)
    if extra:
        row["payload_fingerprint"] = "a" * 64
    return row


def test_delivery_admin_projection_selects_only_contract_columns() -> None:
    row = _delivery_admin_row()
    cursor = ScriptedCursor(one_rows=({"total": 1},), all_rows=((row,),))
    page = MySqlLineDeliveryTaskRepository(FakeConnection(cursor)).list_admin(
        LineDeliveryAdminQuery(page=1, page_size=25)
    )

    assert len(page.items) == 1
    admin_sql = cursor.executed[1][0]
    for internal_column in (
        "payload_fingerprint",
        "idempotency_key",
        "correlation_id",
        "lease_owner",
        "lease_acquired_at_utc",
        "lease_expires_at_utc",
    ):
        assert internal_column not in admin_sql


@pytest.mark.parametrize(
    ("missing", "extra"),
    (("updated_at_utc", False), (None, True)),
)
def test_delivery_admin_projection_rejects_missing_or_extra_columns(
    missing: str | None,
    extra: bool,
) -> None:
    cursor = ScriptedCursor(
        one_rows=({"total": 1},),
        all_rows=((_delivery_admin_row(missing=missing, extra=extra),),),
    )

    with pytest.raises(ValueError, match="shape"):
        MySqlLineDeliveryTaskRepository(FakeConnection(cursor)).list_admin(
            LineDeliveryAdminQuery(page=1, page_size=25)
        )


def test_notification_and_delivery_repositories_cancel_only_their_owned_rows() -> None:
    notification_cursor = ScriptedCursor(all_rows=(({
        "intent_id": 9,
        "delivery_task_id": 19,
    },),))
    lineage = MySqlLineNotificationRepository(
        FakeConnection(notification_cursor)
    ).lock_and_cancel_rule_intents("rule-a", reason="notification_rule_delete")

    assert lineage.intent_ids == (9,)
    assert lineage.task_ids == (LineDeliveryTaskId(19),)
    assert all("line_delivery_tasks" not in sql for sql, _ in notification_cursor.executed)
    assert "FOR UPDATE" in notification_cursor.executed[0][0]

    delivery_cursor = ScriptedCursor(all_rows=(({
        "id": 19,
        "processing_status": "pending",
    },),))
    cancelled = MySqlLineDeliveryTaskRepository(
        FakeConnection(delivery_cursor)
    ).cancel_pending_for_notification_rule(
        lineage.task_ids,
        reason="notification_rule_delete",
    )

    assert cancelled == lineage.task_ids
    assert all("line_notification_intents" not in sql for sql, _ in delivery_cursor.executed)
    assert "FOR UPDATE" in delivery_cursor.executed[0][0]


def test_notification_cancellation_rejects_malformed_or_duplicate_lineage() -> None:
    malformed = ScriptedCursor(all_rows=(({
        "intent_id": 9,
        "delivery_task_id": 19,
        "unexpected": "drift",
    },),))
    with pytest.raises(RuntimeError, match="cancellation_lineage_invalid"):
        MySqlLineNotificationRepository(
            FakeConnection(malformed)
        ).lock_and_cancel_rule_intents("rule-a", reason="notification_rule_delete")

    duplicate_tasks = ScriptedCursor(all_rows=((
        {"intent_id": 9, "delivery_task_id": 19},
        {"intent_id": 10, "delivery_task_id": 19},
    ),))
    with pytest.raises(RuntimeError, match="cancellation_lineage_invalid"):
        MySqlLineNotificationRepository(
            FakeConnection(duplicate_tasks)
        ).lock_and_cancel_rule_intents("rule-a", reason="notification_rule_delete")

    delivery_drift = ScriptedCursor(all_rows=(({
        "id": "19",
        "processing_status": "pending",
        "unexpected": "drift",
    },),))
    with pytest.raises(RuntimeError, match="delivery_task_cancellation_conflict"):
        MySqlLineDeliveryTaskRepository(
            FakeConnection(delivery_drift)
        ).cancel_pending_for_notification_rule(
            (LineDeliveryTaskId(19),),
            reason="notification_rule_delete",
        )


def _rich_menu_attempt_row(
    *,
    correlation_id: str = "line-rich-menu:7",
    outcome: str = "success",
    provider_menu_id: str | None = "richmenu-7",
    error_code: str | None = None,
) -> dict[str, object]:
    return {
        "publication_id": 7,
        "step_name": "create",
        "attempt_number": 1,
        "request_fingerprint": "a" * 64,
        "idempotency_key": "line-rich-menu:7:create:attempt:1",
        "outcome": outcome,
        "provider_menu_id": provider_menu_id,
        "error_code": error_code,
        "attempted_at_utc": NOW.replace(tzinfo=None),
        "correlation_id": correlation_id,
    }


def _rich_menu_attempt_event() -> LineRichMenuStepAttemptEvent:
    return LineRichMenuStepAttemptEvent(
        LineRichMenuPublicationId(7),
        LineRichMenuPublicationStep.CREATE,
        1,
        PreviewFingerprint("a" * 64),
        IdempotencyKey("line-rich-menu:7:create:attempt:1"),
        LineRichMenuStepAttemptOutcome.SUCCESS,
        NOW,
        CorrelationId("line-rich-menu:7"),
        "richmenu-7",
        None,
    )


def test_rich_menu_attempt_events_round_trip_with_typed_shape_and_no_commit() -> None:
    event = _rich_menu_attempt_event()
    append_cursor = ScriptedCursor(one_rows=(_rich_menu_attempt_row(),))
    result = MySqlLineRichMenuPublicationRepository(
        FakeConnection(append_cursor)
    ).append_step_attempt_event(event)

    assert result == event
    assert append_cursor.executed[0][1] == (
        7,
        "create",
        1,
        "a" * 64,
        "line-rich-menu:7:create:attempt:1",
        "success",
        "richmenu-7",
        None,
        NOW.replace(tzinfo=None),
        "line-rich-menu:7",
    )
    assert all("commit" not in sql.lower() for sql, _ in append_cursor.executed)

    list_cursor = ScriptedCursor(all_rows=((_rich_menu_attempt_row(),),))
    events = MySqlLineRichMenuPublicationRepository(
        FakeConnection(list_cursor)
    ).list_step_attempt_events(LineRichMenuPublicationId(7))

    assert events == (event,)
    assert list_cursor.executed[0][1] == (7,)


def test_rich_menu_attempt_event_idempotent_replay_and_collision_fail_closed() -> None:
    event = _rich_menu_attempt_event()
    duplicate_cursor = DuplicateAttemptCursor(
        one_rows=(_rich_menu_attempt_row(), _rich_menu_attempt_row())
    )
    duplicate_result = MySqlLineRichMenuPublicationRepository(
        FakeConnection(duplicate_cursor)
    ).append_step_attempt_event(event)
    assert duplicate_result == event

    collision_rows = _rich_menu_attempt_row(correlation_id="line-rich-menu:other")
    collision_cursor = DuplicateAttemptCursor(
        one_rows=(_rich_menu_attempt_row(), collision_rows)
    )
    with pytest.raises(RuntimeError, match="line_rich_menu_step_attempt_collision"):
        MySqlLineRichMenuPublicationRepository(
            FakeConnection(collision_cursor)
        ).append_step_attempt_event(event)


def test_rich_menu_attempt_event_rejects_row_shape_drift_and_failed_payload_mismatch() -> None:
    malformed = _rich_menu_attempt_row()
    malformed["unexpected"] = "drift"
    with pytest.raises(ValueError, match="line_rich_menu_step_attempt_row_shape_invalid"):
        MySqlLineRichMenuPublicationRepository(
            FakeConnection(ScriptedCursor(all_rows=((malformed,),)))
        ).list_step_attempt_events(LineRichMenuPublicationId(7))

    with pytest.raises(ValueError, match="failed Rich Menu attempt"):
        LineRichMenuStepAttemptEvent(
            LineRichMenuPublicationId(7),
            LineRichMenuPublicationStep.CREATE,
            1,
            PreviewFingerprint("a" * 64),
            IdempotencyKey("line-rich-menu:7:create:attempt:2"),
            LineRichMenuStepAttemptOutcome.TIMEOUT,
            NOW,
            CorrelationId("line-rich-menu:7"),
            "richmenu-7",
            "timeout",
        )


def test_rich_menu_apply_locks_configuration_root_and_never_uses_legacy_preview_table() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            {
                "definition_snapshot": (
                    '{"menus":[{"enabled":true,"id":"default_menu"}]}'
                )
            },
        )
    )
    command = QueueLineRichMenuPublicationCommand(
        menu_definition_id="default_menu",
        configuration_revision=LineConfigurationRevision(7),
        actor=ActorContext("17"),
        idempotency_key=IdempotencyKey("rich-menu-apply:stateless"),
        correlation_id=CorrelationId("rich-menu-apply:stateless-correlation"),
        preview_id=999,
        preview_config_revision="not-used-by-repository",
        preview_config_fingerprint="not-used-by-repository",
        previewed_by_admin_user_id=17,
    )

    result = MySqlLineRichMenuPublicationRepository(
        FakeConnection(cursor)
    ).queue(command)

    assert result.publication.configuration_revision == LineConfigurationRevision(7)
    statements = [sql for sql, _ in cursor.executed]
    assert "FOR UPDATE" in statements[0]
    assert all("line_rich_menu_publish_previews" not in sql for sql in statements)
    assert not any(sql.startswith("UPDATE line_rich_menu_publish_previews") for sql in statements)


def test_rich_menu_publication_list_page_uses_db_limit_offset_and_total_over_100_rows() -> None:
    rows = (
        {
            "id": 101,
            "menu_definition_id": "default_menu",
            "configuration_revision": 7,
            "publication_status": LineRichMenuPublicationStatus.QUEUED.value,
        },
        {
            "id": 100,
            "menu_definition_id": "default_menu",
            "configuration_revision": 7,
            "publication_status": LineRichMenuPublicationStatus.PUBLISHED.value,
        },
    )
    cursor = ScriptedCursor(one_rows=({"total": 101},), all_rows=(rows,))
    page = MySqlLineRichMenuPublicationRepository(
        FakeConnection(cursor)
    ).list_page(
        LineRichMenuPublicationQuery(
            menu_definition_id="default_menu",
            page_size=2,
        ),
        offset=100,
    )

    assert page.total == 101
    assert page.offset == 100
    assert page.page_size == 2
    assert tuple(item.publication_id.value for item in page.items) == (101, 100)
    assert cursor.executed[0][1] == ("default_menu",)
    assert cursor.executed[1][1] == ("default_menu", 2, 100)
    assert "menu_definition_id=%s" in cursor.executed[0][0]
    assert "menu_definition_id=%s" in cursor.executed[1][0]
    assert "LIMIT %s OFFSET %s" in cursor.executed[1][0]


def test_rich_menu_publication_exact_revision_query_has_no_history_limit() -> None:
    rows = (
        {
            "id": 12,
            "menu_definition_id": "customer_menu",
            "configuration_revision": 8,
            "publication_status": LineRichMenuPublicationStatus.PUBLISHED.value,
        },
        {
            "id": 11,
            "menu_definition_id": "staff_menu",
            "configuration_revision": 8,
            "publication_status": LineRichMenuPublicationStatus.PUBLISHING.value,
        },
    )
    cursor = ScriptedCursor(all_rows=(rows,))

    result = MySqlLineRichMenuPublicationRepository(
        FakeConnection(cursor)
    ).list_for_configuration_revision(LineConfigurationRevision(8))

    assert tuple(item.menu_definition_id for item in result) == (
        "customer_menu",
        "staff_menu",
    )
    sql, parameters = cursor.executed[0]
    assert parameters == (8,)
    assert "configuration_revision=%s" in sql
    assert "LIMIT" not in sql


def _rich_menu_cleanup_work_row() -> dict[str, object]:
    return {
        "id": 7,
        "menu_definition_id": "default_menu",
        "configuration_revision": 3,
        "publication_status": LineRichMenuPublicationStatus.PUBLISHED.value,
        "definition_snapshot": '{"id":"default_menu"}',
        "image_object_reference": "rich-menu/default.png",
        "provider_menu_id": "new-menu",
        "previous_provider_menu_id": "old-menu",
        "attempt_count": 1,
        "max_attempts": 3,
        "lease_owner": "worker-1",
        "lease_expires_at_utc": NOW.replace(tzinfo=None),
        "correlation_id": "line-rich-menu:7",
    }


def test_rich_menu_claim_returns_typed_cleanup_only_work_without_downgrading_published() -> None:
    row = _rich_menu_cleanup_work_row()
    cursor = ScriptedCursor(one_rows=(row,), all_rows=((row,),))
    repository = MySqlLineRichMenuPublicationRepository(FakeConnection(cursor))

    claimed = repository.claim(
        ClaimLineRichMenuPublicationsQuery("worker-1", NOW, 5)
    )

    assert len(claimed) == 1
    assert isinstance(claimed[0], LineRichMenuCleanupWorkItem)
    assert claimed[0].publication.status is LineRichMenuPublicationStatus.PUBLISHED
    assert claimed[0].published_provider_menu_id == "new-menu"
    assert claimed[0].previous_provider_menu_id == "old-menu"
    update_sql, update_parameters = cursor.executed[1]
    assert "publication_status='publishing'" not in update_sql
    assert update_parameters[-1] == 7
    claim_sql = cursor.executed[0][0]
    assert "publication_status='published'" in claim_sql
    assert "step_name='cleanup'" in claim_sql
    assert "NOT EXISTS" in claim_sql


def test_rich_menu_cleanup_claim_fails_closed_when_lease_update_is_lost() -> None:
    row = _rich_menu_cleanup_work_row()
    cursor = LostClaimCursor(all_rows=((row,),))
    repository = MySqlLineRichMenuPublicationRepository(FakeConnection(cursor))

    with pytest.raises(RuntimeError, match="line_rich_menu_publication_claim_lost"):
        repository.claim(ClaimLineRichMenuPublicationsQuery("worker-1", NOW, 5))


def test_rich_menu_cleanup_claim_query_excludes_acknowledged_or_live_leased_rows() -> None:
    cursor = ScriptedCursor(all_rows=((),))
    repository = MySqlLineRichMenuPublicationRepository(FakeConnection(cursor))

    assert repository.claim(
        ClaimLineRichMenuPublicationsQuery("worker-1", NOW, 5)
    ) == ()

    claim_sql, parameters = cursor.executed[0]
    assert "lease_owner IS NULL" in claim_sql
    assert "lease_expires_at_utc<=%s" in claim_sql
    assert "NOT EXISTS" in claim_sql
    assert parameters.count(NOW.replace(tzinfo=None)) >= 4


def test_webhook_claim_recovers_exhausted_leases_and_binds_due_clocks() -> None:
    cursor = ScriptedCursor(all_rows=((),))
    repository = MySqlLineWebhookInboxRepository(FakeConnection(cursor))

    claimed = repository.claim(ClaimLineWebhookEventsQuery("worker-1", NOW, 10))

    assert claimed == ()
    exhausted_parameters = cursor.executed[0][1]
    due_parameters = cursor.executed[1][1]
    assert exhausted_parameters[0] == exhausted_parameters[1]
    assert due_parameters[0] == due_parameters[1] == due_parameters[2]
    assert due_parameters[3] == 10


def test_existing_unbound_identity_is_updated_not_inserted() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            {
                "line_user_id": "U-staff",
                "binding_status": "unbound",
                "subject_type": None,
                "subject_reference": None,
                "aggregate_version": 0,
            },
        )
    )
    repository = MySqlLineIdentityRepository(FakeConnection(cursor))

    result = repository.save_claim(
        LineIdentityClaim(
            LineUserId("U-staff"),
            LineBindingSubjectType.STAFF,
            "staff:8",
        ),
        ExpectedVersion(0),
    )

    statements = [sql for sql, _parameters in cursor.executed]
    assert result.version == ExpectedVersion(1)
    assert any(sql.startswith("UPDATE line_identity_bindings") for sql in statements)
    assert not any(sql.startswith("INSERT INTO line_identity_bindings ") for sql in statements)


def test_identity_repository_lists_only_bound_subject_audience() -> None:
    cursor = ScriptedCursor(
        all_rows=(
            (
                {
                    "line_user_id": "U-union",
                    "binding_status": "bound",
                    "subject_type": "admin",
                    "subject_reference": "7",
                    "aggregate_version": 1,
                },
            ),
        )
    )
    repository = MySqlLineIdentityRepository(FakeConnection(cursor))

    result = repository.list_bound_by_subject_type(LineBindingSubjectType.ADMIN)

    assert result[0].line_user_id == LineUserId("U-union")
    assert cursor.executed[0][1] == ("admin",)
    assert "binding_status='bound'" in cursor.executed[0][0]


def test_group_binding_idempotency_returns_before_current_state_validation() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            {
                "case_no": "CASE-1",
                "before_group_id": None,
                "resulting_group_id": "C-group-1",
                "expected_version": 0,
                "binding_fingerprint": "placeholder",
            },
        )
    )
    command = BindLineOrderGroupCommand(
        "CASE-1",
        LineGroupId("C-group-1"),
        ExpectedVersion(0),
        ActorContext("admin:1"),
        IdempotencyKey("bind:CASE-1:C-group-1"),
        CorrelationId("correlation:CASE-1"),
    )
    from domains.line.order_group import (
        LineOrderGroupBindingSnapshot,
        LineOrderGroupBindingStatus,
        build_order_group_binding_candidate,
    )

    candidate = build_order_group_binding_candidate(
        LineOrderGroupBindingSnapshot(
            "CASE-1", None, LineOrderGroupBindingStatus.UNBOUND, ExpectedVersion(0)
        ),
        group_id=command.group_id,
        expected_version=command.expected_version,
        actor=command.actor,
    )
    cursor.one_rows[0]["binding_fingerprint"] = candidate.fingerprint.value

    result = MySqlLineOrderGroupBindingRepository(FakeConnection(cursor)).bind(command)

    assert result.outcome is LineOrderGroupCommandOutcome.EXISTING
    assert len(cursor.executed) == 1


def test_line_unit_of_work_owns_one_transaction_and_all_repositories() -> None:
    connection = TransactionConnection()

    with LineMySqlUnitOfWork(connection) as unit_of_work:
        assert unit_of_work.webhook_inbox is not None
        assert unit_of_work.delivery_tasks is not None
        assert unit_of_work.configurations is not None
        assert unit_of_work.rich_menu_publications is not None
        assert unit_of_work.media_metadata is not None
        assert unit_of_work.order_groups is not None
        unit_of_work.commit()

    assert connection.actions == ["begin", "commit"]
