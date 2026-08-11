"""Focused contract tests for canonical LINE MySQL repository adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from domains.line.identities import LineGroupId, LineUserId, LineWebhookEventId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityClaim
from domains.line.webhook import LineWebhookProcessingStatus
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityRepository,
)
from infrastructure.mysql.line_media_order_group_repository import (
    MySqlLineOrderGroupBindingRepository,
)
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from infrastructure.mysql.line_webhook_inbox_repository import (
    MySqlLineWebhookInboxRepository,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery
from subsystems.line.webhook_contracts import ClaimLineWebhookEventsQuery
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    LineOrderGroupCommandOutcome,
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
