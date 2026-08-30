"""File: test_service_day_log_repository.py
Description: 驗證寶寶日誌 repository 的鎖定與 terminal replay owner 邊界。"""

from datetime import date, datetime, timezone

import pytest

from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from domains.scheduling.service_day_log import ServiceDayLogIntent
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling.service_day_log_workflow import (
    ApplyServiceDayLog,
    ControlledServiceDayLogAttachment,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows):
        self.cursor_value = FakeCursor(rows)

    def cursor(self):
        return self.cursor_value


def _command(line_user_id="U-caregiver"):
    return ApplyServiceDayLog(9, line_user_id, 12, ServiceDayLogIntent(date(2026, 8, 16), "寶寶正常", ()), "log-key", PreviewFingerprint("a" * 64))


def _row(**overrides):
    return {"id": 1, "case_no": "CASE-1", "assignment_id": 12, "staff_id": 9, "staff_line_user_id": "U-caregiver", "service_date": date(2026, 8, 16), "baby_log_text": "寶寶正常", "requires_cooking": 0, "content_fingerprint": "a" * 64, **overrides}


def test_assignment_preview_query_does_not_lock_but_apply_does() -> None:
    connection = FakeConnection([{"case_no": "CASE-1", "requires_cooking": 0}, {"case_no": "CASE-1", "requires_cooking": 0}])
    repository = MySqlServiceDayLogRepository(connection)

    repository.load_assignment(9, 12, date(2026, 8, 16), for_update=False)
    repository.load_assignment(9, 12, date(2026, 8, 16), for_update=True)

    assert "FOR UPDATE" not in connection.cursor_value.executed[0][0]
    assert connection.cursor_value.executed[1][0].endswith("FOR UPDATE")


def test_terminal_replay_requires_exact_staff_owner_and_fingerprint() -> None:
    repository = MySqlServiceDayLogRepository(FakeConnection([_row()]))

    result = repository.load_replay(_command())

    assert result is not None and result.outcome == "existing"
    with pytest.raises(ValueError, match="service_day_log_idempotency_conflict"):
        MySqlServiceDayLogRepository(FakeConnection([_row()])).load_replay(_command("U-other"))


class _TransactionCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executed = []
        self.rowcount = 0
        self.lastrowid = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))
        if sql.startswith("SELECT"):
            self.rowcount = 0
            return
        self.rowcount = 1
        self.lastrowid = self.connection.next_id
        self.connection.next_id += 1
        self.connection.pending.append((sql, params))

    def fetchone(self):
        if self.executed and "FROM controlled_file_objects" in self.executed[-1][0]:
            return {
                "object_key": self.connection.object_key,
                "content_sha256": "a" * 64,
                "owner_type": "scheduling",
                "purpose": "meal_photo",
            }
        return None


class _TransactionConnection:
    def __init__(self):
        self.pending = []
        self.committed = []
        self.next_id = 100
        self.cursors = []
        self.object_key = canonical_scheduling_object_key(
            assignment_id=12,
            service_date=date(2026, 8, 16),
            attachment_kind="meal_photo",
            sequence=1,
            sha256_digest="a" * 64,
        )

    def begin(self):
        self.pending.clear()

    def commit(self):
        self.committed.extend(self.pending)
        self.pending.clear()

    def rollback(self):
        self.pending.clear()

    def cursor(self):
        cursor = _TransactionCursor(self)
        self.cursors.append(cursor)
        return cursor


class _OuterUnitOfWork:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.begin()
        return self

    def __exit__(self, exception_type, *_args):
        if exception_type is not None:
            self.connection.rollback()
        return False

    def commit(self):
        self.connection.commit()


class _ReferenceFinalizePort:
    def __init__(self, connection, *, fail_on_finalize=False):
        self.connection = connection
        self.calls = []
        self.fail_on_finalize = fail_on_finalize

    def assert_controlled_file_exists(self, object_id):
        self.calls.append(("exists", object_id))

    def create_scheduling_reference(self, reference):
        self.calls.append(("reference", reference))
        self.connection.pending.append(("controlled_file_reference", reference))
        return reference

    def create_finalize_intent(self, intent):
        self.calls.append(("finalize", intent))
        if self.fail_on_finalize:
            raise ValueError("controlled_file_finalize_reference_missing")
        self.connection.pending.append(("controlled_file_finalize_intent", intent))


def _controlled_command():
    return ApplyServiceDayLog(
        9,
        "U-caregiver",
        12,
        ServiceDayLogIntent(date(2026, 8, 16), "寶寶正常", ()),
        "log-key",
        PreviewFingerprint("a" * 64),
        controlled_file_attachments=(
            ControlledServiceDayLogAttachment(
                "cf_1234567890abcdef1234567890abcdef",
                "cfs_1234567890abcdef1234567890abcdef",
                "a" * 64,
                created_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            ),
        ),
    )


def test_controlled_file_bridge_uses_one_connection_and_writes_reference_intent_before_commit():
    connection = _TransactionConnection()
    port = _ReferenceFinalizePort(connection)
    repository = MySqlServiceDayLogRepository(
        connection, reference_finalize_repository=port
    )

    with _OuterUnitOfWork(connection) as unit_of_work:
        result = repository.submit(
            _controlled_command(),
            {"case_no": "CASE-1", "requires_cooking": False},
        )
        unit_of_work.commit()

    assert result.outcome == "created"
    assert [call[0] for call in port.calls] == ["exists", "reference", "finalize"]
    assert len(connection.committed) == 6  # log, event, attachment, outbox + 2 typed facts
    assert any(
        "controlled_file_object_id" in sql and "provider_media_id" in sql
        for sql, _params in connection.committed
        if isinstance(sql, str)
    )


def test_controlled_file_bridge_failure_rolls_back_log_attachment_and_reference_facts():
    connection = _TransactionConnection()
    port = _ReferenceFinalizePort(connection, fail_on_finalize=True)
    repository = MySqlServiceDayLogRepository(
        connection, reference_finalize_repository=port
    )

    with pytest.raises(ValueError, match="controlled_file_finalize_reference_missing"):
        with _OuterUnitOfWork(connection):
            repository.submit(
                _controlled_command(),
                {"case_no": "CASE-1", "requires_cooking": False},
            )

    assert connection.committed == []
    assert connection.pending == []
    assert [call[0] for call in port.calls] == ["exists", "reference", "finalize"]


def test_controlled_file_bridge_rejects_noncanonical_object_key_before_attachment():
    connection = _TransactionConnection()
    connection.object_key = "scheduling/service-day/v1/12/2026-08-16/meal_photo/1/wrong"
    port = _ReferenceFinalizePort(connection)
    repository = MySqlServiceDayLogRepository(
        connection, reference_finalize_repository=port
    )

    with pytest.raises(ValueError, match="controlled_file_object_key_mismatch"):
        with _OuterUnitOfWork(connection):
            repository.submit(
                _controlled_command(),
                {"case_no": "CASE-1", "requires_cooking": False},
            )

    assert connection.committed == []
    assert connection.pending == []
    assert port.calls == []


def test_legacy_provider_media_path_does_not_create_1015_facts():
    connection = _TransactionConnection()
    repository = MySqlServiceDayLogRepository(connection)
    command = ApplyServiceDayLog(
        9,
        "U-caregiver",
        12,
        ServiceDayLogIntent(
            date(2026, 8, 16), "寶寶正常", ("line-media-legacy",)
        ),
        "log-key",
        PreviewFingerprint("a" * 64),
    )

    with _OuterUnitOfWork(connection) as unit_of_work:
        repository.submit(command, {"case_no": "CASE-1", "requires_cooking": False})
        unit_of_work.commit()

    sql_text = " ".join(sql for sql, _params in connection.committed if isinstance(sql, str))
    assert "controlled_file_references" not in sql_text
    assert "controlled_file_finalize_intents" not in sql_text
