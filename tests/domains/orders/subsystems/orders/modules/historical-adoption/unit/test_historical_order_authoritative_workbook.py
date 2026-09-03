from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from domains.orders.historical_adoption import (
    HistoricalOrderCurrentFacts,
    HistoricalOrderResult,
    HistoricalOrderSourceFacts,
    HistoricalOrderSourceStatus,
    build_historical_order_candidate,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql import historical_order_workbook_import_repository as repository_module
from subsystems.orders import historical_order_workbook_import as import_module
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbook
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderAbsenceCancellation,
    HistoricalOrderWorkbookConflict,
    HistoricalOrderWorkbookImportService,
)
from subsystems.orders.order_lifecycle_command_envelope import _validate_order_row


BUSINESS_DATE = date(2026, 9, 1)


def test_on_time_historical_start_is_service_completion_not_unserved():
    current = HistoricalOrderCurrentFacts(
        "CASE-1",
        "客戶甲",
        OrderLifecycleStatus.DISCUSSION,
        3,
        date(2025, 1, 3),
        None,
        None,
    )
    source = HistoricalOrderSourceFacts(
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        date(2025, 1, 3),
        date(2025, 1, 31),
    )

    candidate = build_historical_order_candidate(current, source, BUSINESS_DATE)

    assert candidate.result is HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED
    assert candidate.after_status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert candidate.date_patch == (
        ("actual_start_date", date(2025, 1, 3)),
        ("actual_end_date", date(2025, 1, 31)),
    )


def test_future_historical_start_remains_unserved():
    current = HistoricalOrderCurrentFacts(
        "CASE-1",
        "客戶甲",
        OrderLifecycleStatus.DISCUSSION,
        3,
        date(2026, 9, 2),
        None,
        None,
    )
    source = HistoricalOrderSourceFacts(
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        date(2026, 9, 2),
        date(2026, 9, 30),
    )

    candidate = build_historical_order_candidate(current, source, BUSINESS_DATE)

    assert candidate.result is HistoricalOrderResult.HISTORICAL_UNSERVED
    assert candidate.after_status is OrderLifecycleStatus.HISTORICAL_UNSERVED
    assert candidate.date_patch == ()


def test_service_ending_on_business_date_remains_in_service():
    current = HistoricalOrderCurrentFacts(
        "CASE-1",
        "客戶甲",
        OrderLifecycleStatus.DISCUSSION,
        3,
        date(2026, 8, 1),
        None,
        None,
    )
    source = HistoricalOrderSourceFacts(
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        date(2026, 8, 1),
        BUSINESS_DATE,
    )

    candidate = build_historical_order_candidate(current, source, BUSINESS_DATE)

    assert candidate.result is HistoricalOrderResult.HISTORICAL_IN_SERVICE
    assert candidate.after_status is OrderLifecycleStatus.HISTORICAL_IN_SERVICE
    assert candidate.date_patch == (
        ("actual_start_date", date(2026, 8, 1)),
        ("actual_end_date", BUSINESS_DATE),
    )


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


class _WorkflowThatMustRemainUnused:
    def preview(self, _row):
        raise AssertionError("empty workbook must not preview a row")

    def preview_in_current_unit_of_work(self, _row, *, for_update):
        raise AssertionError(f"empty workbook must not lock a row: {for_update}")

    def apply_in_current_unit_of_work(self, _request):
        raise AssertionError("empty workbook must not apply a row")


class _WorkbookRepository:
    def __init__(self, preview_candidates, locked_candidates=None):
        self.preview_candidates = tuple(preview_candidates)
        self.locked_candidates = (
            self.preview_candidates
            if locked_candidates is None
            else tuple(locked_candidates)
        )
        self.locked_keys = set()
        self.find_calls = []
        self.cancel_calls = []
        self.saved = None

    def acquire_lock(self, key):
        if key in self.locked_keys:
            return False
        self.locked_keys.add(key)
        return True

    def release_lock(self, key):
        self.locked_keys.remove(key)

    def load_receipt(self, _key):
        return None

    def claim(self, _key, _digest, _correlation_id):
        return "created"

    def save_receipt(self, key, digest, preview_fingerprint, actor, result):
        self.saved = (key, digest, preview_fingerprint, actor, result)

    def find_open_review_identities(self, _source_event_identities):
        return ()

    def find_absent_orders(self, source_case_nos, *, for_update):
        self.find_calls.append((source_case_nos, for_update))
        return self.locked_candidates if for_update else self.preview_candidates

    def cancel_absent_orders(
        self,
        candidates,
        *,
        workbook_key,
        source_content_digest,
        actor,
        correlation_id,
    ):
        self.cancel_calls.append(
            (
                candidates,
                workbook_key,
                source_content_digest,
                actor,
                correlation_id,
            )
        )
        return len(candidates)


def _empty_workbook():
    return HistoricalOrderWorkbook(
        "a" * 64,
        "b" * 64,
        "歷史訂單",
        (),
    )


def test_preview_and_apply_cancel_every_database_order_absent_from_workbook(monkeypatch):
    candidates = (
        HistoricalOrderAbsenceCancellation(
            "CASE-OLD-1", OrderLifecycleStatus.DISCUSSION, 3
        ),
        HistoricalOrderAbsenceCancellation(
            "CASE-OLD-2", OrderLifecycleStatus.PENDING_COMPLETION, 0
        ),
    )
    repository = _WorkbookRepository(candidates)
    unit_of_work = _UnitOfWork()
    monkeypatch.setattr(
        import_module,
        "load_historical_order_workbook",
        lambda _path: _empty_workbook(),
    )
    service = HistoricalOrderWorkbookImportService(
        repository,
        _WorkflowThatMustRemainUnused(),
        lambda: unit_of_work,
    )

    preview = service.preview("ignored.xlsx")
    receipt = service.apply(
        "ignored.xlsx",
        "historical-authoritative-1",
        preview.preview_fingerprint,
        "operator",
        "historical-authoritative-correlation",
    )

    assert preview.absent_order_cancellation_count == 2
    assert receipt.absent_order_cancellation_count == 2
    assert receipt.source_row_count == 0
    assert unit_of_work.committed is True
    assert repository.cancel_calls == [
        (
            candidates,
            "historical-authoritative-1",
            "a" * 64,
            "operator",
            "historical-authoritative-correlation",
        )
    ]
    assert repository.saved[-1]["absent_order_cancellation_count"] == 2


def test_apply_rejects_changed_absence_set_after_preview(monkeypatch):
    preview_candidate = HistoricalOrderAbsenceCancellation(
        "CASE-OLD", OrderLifecycleStatus.DISCUSSION, 3
    )
    locked_candidate = HistoricalOrderAbsenceCancellation(
        "CASE-OLD", OrderLifecycleStatus.ESTABLISHED, 4
    )
    repository = _WorkbookRepository(
        (preview_candidate,),
        locked_candidates=(locked_candidate,),
    )
    unit_of_work = _UnitOfWork()
    monkeypatch.setattr(
        import_module,
        "load_historical_order_workbook",
        lambda _path: _empty_workbook(),
    )
    service = HistoricalOrderWorkbookImportService(
        repository,
        _WorkflowThatMustRemainUnused(),
        lambda: unit_of_work,
    )
    preview = service.preview("ignored.xlsx")

    with pytest.raises(
        HistoricalOrderWorkbookConflict,
        match="historical_order_absence_preview_stale",
    ):
        service.apply(
            "ignored.xlsx",
            "historical-authoritative-stale",
            preview.preview_fingerprint,
            "operator",
            "historical-authoritative-stale-correlation",
        )

    assert repository.cancel_calls == []
    assert unit_of_work.committed is False


class _RowsCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.rowcount = 0

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))
        if statement.startswith("UPDATE orders") or statement.startswith(
            "INSERT INTO order_lifecycle_state_events"
        ):
            self.rowcount = 1

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _RowsConnection:
    def __init__(self, rows):
        self.cursor_value = _RowsCursor(rows)

    def cursor(self):
        return self.cursor_value


def test_repository_finds_only_nonlisted_non_cancelled_orders():
    connection = _RowsConnection(
        (
            {"case_no": "CASE-IN", "status": "洽談中", "lifecycle_version": 1},
            {"case_no": "CASE-OUT", "status": "訂單成立", "lifecycle_version": 2},
        )
    )
    repository = repository_module.HistoricalOrderWorkbookImportRepository(connection)

    result = repository.find_absent_orders(("CASE-IN",), for_update=True)

    assert result == (
        HistoricalOrderAbsenceCancellation(
            "CASE-OUT", OrderLifecycleStatus.ESTABLISHED, 2
        ),
    )
    statement, parameters = connection.cursor_value.executed[0]
    assert statement.endswith("FOR UPDATE")
    assert parameters == (OrderLifecycleStatus.CANCELLED.value,)
    assert repository._lock_name("one") == repository._lock_name("two")
    assert repository._lock_name("one") == "order-history:authoritative-workbook"


def test_repository_cancels_absent_incomplete_order_with_control_and_lifecycle_event(
    monkeypatch,
):
    connection = _RowsConnection(())
    envelope = SimpleNamespace(
        current_status=OrderLifecycleStatus.PENDING_COMPLETION.value,
        existing_control_event=None,
        existing_lifecycle_event=None,
    )
    locked = []
    controls = []

    def lock(cursor, case_no, expected_version, idempotency_key, **options):
        locked.append((cursor, case_no, expected_version, idempotency_key, options))
        return envelope

    def apply_control(cursor, actual_envelope, command):
        controls.append((cursor, actual_envelope, command))
        return SimpleNamespace(event_id=81)

    monkeypatch.setattr(
        repository_module,
        "lock_order_lifecycle_command_envelope",
        lock,
    )
    monkeypatch.setattr(
        repository_module,
        "apply_order_lifecycle_control_command",
        apply_control,
    )
    repository = repository_module.HistoricalOrderWorkbookImportRepository(connection)
    candidate = HistoricalOrderAbsenceCancellation(
        "CASE-INCOMPLETE",
        OrderLifecycleStatus.PENDING_COMPLETION,
        0,
    )

    count = repository.cancel_absent_orders(
        (candidate,),
        workbook_key="authoritative-workbook-key",
        source_content_digest="a" * 64,
        actor="operator",
        correlation_id="authoritative-workbook-correlation",
    )

    assert count == 1
    assert locked[0][1:3] == ("CASE-INCOMPLETE", 0)
    assert locked[0][-1] == {"allow_incomplete_order": True}
    assert controls[0][2].action == "activate"
    assert controls[0][2].reason == (
        "historical_order_adoption:authoritative_workbook_absence"
    )
    update = next(
        call
        for call in connection.cursor_value.executed
        if call[0].startswith("UPDATE orders")
    )
    assert update[1] == (
        OrderLifecycleStatus.CANCELLED.value,
        1,
        "CASE-INCOMPLETE",
        OrderLifecycleStatus.PENDING_COMPLETION.value,
        0,
    )
    lifecycle = next(
        call
        for call in connection.cursor_value.executed
        if call[0].startswith("INSERT INTO order_lifecycle_state_events")
    )
    assert lifecycle[1][0:3] == (
        "CASE-INCOMPLETE",
        OrderLifecycleStatus.PENDING_COMPLETION.value,
        OrderLifecycleStatus.CANCELLED.value,
    )
    assert "historical_order_authoritative_workbook_absence" in lifecycle[1][-1]


def test_command_envelope_allows_incomplete_order_only_for_explicit_caller():
    row = {
        "case_no": "CASE-INCOMPLETE",
        "status": OrderLifecycleStatus.PENDING_COMPLETION.value,
        "lifecycle_version": 0,
        "service_days": 0,
        "cancel_reason": None,
        "actual_start_date": None,
        "actual_end_date": None,
        "service_start_time": "09:00:00",
        "service_end_time": None,
        "service_end_day_offset": None,
    }

    with pytest.raises(ValueError, match="pending-completion"):
        _validate_order_row(row, "CASE-INCOMPLETE")

    assert _validate_order_row(
        row,
        "CASE-INCOMPLETE",
        allow_incomplete_order=True,
    ) == (OrderLifecycleStatus.PENDING_COMPLETION.value, 0, 0)
