from __future__ import annotations

from datetime import date

import pytest
from openpyxl import Workbook

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_calendar_assignment_remediation import (
    HistoricalCalendarAssignmentCaseFacts,
    HistoricalCalendarAssignmentRemediationApplication,
    HistoricalCalendarAssignmentRemediationError,
)


_CASE = "115000001"
_CLIENT = "楊洋玲"
_STAFF = "黃欣"
_START = date(2025, 10, 7)
_END = date(2025, 11, 17)


def test_repairable_workbook_creates_only_completed_assignment(tmp_path):
    path = _workbook(tmp_path)
    repository = _Repository()
    unit_of_work = _UnitOfWorkFactory()
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        unit_of_work,
    )

    preview = application.preview(path, _CASE, 1)

    assert preview.apply_allowed is True
    assert preview.disposition == "create_completed_assignment"
    assert preview.staff_id == 11
    assert preview.staff_name == _STAFF
    assert preview.start_date == _START
    assert preview.end_date == _END
    assert preview.existing_assignment_id is None

    receipt = application.apply(
        path,
        _CASE,
        1,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-162:create",
        "test-operator",
        "repair historical calendar completed assignment",
    )

    assert receipt.created is True
    assert receipt.assignment_id == 91
    assert receipt.replayed is False
    assert repository.append_calls == [(_CASE, 11, _START, _END)]
    assert repository.case.status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert repository.case.lifecycle_version == 7
    assert unit_of_work.commits == 1
    stored = repository.receipts[
        (
            "orders_historical_calendar_assignment_remediation/v1",
            "issue-162:create",
        )
    ]
    assert stored["actor"] == "test-operator"
    assert stored["reason"] == "repair historical calendar completed assignment"


def test_existing_completed_assignment_is_reused_without_duplicate_write(tmp_path):
    path = _workbook(tmp_path)
    repository = _Repository(existing_assignment_id=77)
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        _UnitOfWorkFactory(),
    )

    preview = application.preview(path, _CASE, 1)
    assert preview.disposition == "reuse_existing"
    assert preview.existing_assignment_id == 77

    receipt = application.apply(
        path,
        _CASE,
        1,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-162:reuse",
        "test-operator",
        "confirm existing historical assignment",
    )

    assert receipt.created is False
    assert receipt.assignment_id == 77
    assert repository.append_calls == []


@pytest.mark.parametrize(
    ("staff_name", "staff_ids", "expected_blocker"),
    [
        (None, (), "historical_calendar_assignment_staff_missing"),
        (_STAFF, (11, 12), "historical_calendar_assignment_staff_ambiguous"),
    ],
)
def test_missing_or_ambiguous_staff_is_blocked(
    tmp_path,
    staff_name,
    staff_ids,
    expected_blocker,
):
    path = _workbook(tmp_path, staff_name=staff_name)
    repository = _Repository(staff_ids=staff_ids)
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        _UnitOfWorkFactory(),
    )

    preview = application.preview(path, _CASE, 1)

    assert preview.apply_allowed is False
    assert expected_blocker in preview.blockers
    with pytest.raises(
        HistoricalCalendarAssignmentRemediationError,
        match="historical_calendar_assignment_blocked",
    ):
        application.apply(
            path,
            _CASE,
            1,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            f"issue-162:{expected_blocker}",
            "test-operator",
            "blocked historical assignment repair",
        )
    assert repository.append_calls == []


def test_invalid_source_date_is_explicitly_blocked(tmp_path):
    path = _workbook(tmp_path, start_date="not-a-date")
    repository = _Repository()
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        _UnitOfWorkFactory(),
    )

    preview = application.preview(path, _CASE, 1)

    assert preview.apply_allowed is False
    assert "historical_calendar_assignment_dates_missing" in preview.blockers
    assert "historical_calendar_assignment_dates_invalid" in preview.blockers
    assert repository.append_calls == []


def test_stale_lifecycle_version_rejects_apply_before_write(tmp_path):
    path = _workbook(tmp_path)
    repository = _Repository()
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        _UnitOfWorkFactory(),
    )
    preview = application.preview(path, _CASE, 1)
    repository.case = HistoricalCalendarAssignmentCaseFacts(
        _CASE,
        _CLIENT,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        8,
    )

    with pytest.raises(
        HistoricalCalendarAssignmentRemediationError,
        match="historical_calendar_assignment_stale_preview",
    ):
        application.apply(
            path,
            _CASE,
            1,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-162:stale",
            "test-operator",
            "stale repair attempt",
        )

    assert repository.append_calls == []


def test_idempotent_replay_returns_same_assignment_without_second_write(tmp_path):
    path = _workbook(tmp_path)
    repository = _Repository()
    application = HistoricalCalendarAssignmentRemediationApplication(
        repository,
        _UnitOfWorkFactory(),
    )
    preview = application.preview(path, _CASE, 1)
    arguments = (
        path,
        _CASE,
        1,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-162:replay",
        "test-operator",
        "repair historical calendar assignment",
    )

    first = application.apply(*arguments)
    second = application.apply(*arguments)

    assert first.assignment_id == second.assignment_id == 91
    assert first.replayed is False
    assert second.replayed is True
    assert repository.append_calls == [(_CASE, 11, _START, _END)]


def _workbook(
    tmp_path,
    *,
    staff_name=_STAFF,
    start_date=_START,
    end_date=_END,
):
    path = tmp_path / "historical-orders.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "client_name",
            "case_no",
            "start_date",
            "end_date",
            "status",
            "staff_name",
        ]
    )
    sheet.append([_CLIENT, _CASE, start_date, end_date, 1, staff_name])
    workbook.save(path)
    workbook.close()
    return path


class _Repository:
    def __init__(
        self,
        *,
        existing_assignment_id=None,
        staff_ids=(11,),
    ):
        self.case = HistoricalCalendarAssignmentCaseFacts(
            _CASE,
            _CLIENT,
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            7,
        )
        self.staff_ids = tuple(staff_ids)
        self.existing_assignment_id = existing_assignment_id
        self.append_calls = []
        self.receipts = {}

    def load_case(self, case_no, *, for_update):
        del for_update
        return self.case if case_no == self.case.case_no else None

    def resolve_staff(self, name, *, for_update):
        del for_update
        return self.staff_ids if name == _STAFF else ()

    def find_matching_completed_assignment(
        self,
        case_no,
        staff_id,
        start_date,
        end_date,
        *,
        for_update,
    ):
        del for_update
        assert case_no == _CASE
        assert staff_id == 11
        assert start_date == _START
        assert end_date == _END
        return self.existing_assignment_id

    def append_completed_assignment(
        self,
        case_no,
        staff_id,
        start_date,
        end_date,
    ):
        self.append_calls.append((case_no, staff_id, start_date, end_date))
        self.existing_assignment_id = 91
        return 91

    def load_receipt(self, family, key):
        stored = self.receipts.get((family, key))
        if stored is None:
            return None
        return {
            "request_fingerprint": stored["request_fingerprint"],
            "result_snapshot": stored["result_snapshot"],
        }

    def save_receipt(
        self,
        family,
        key,
        request_fingerprint,
        preview_fingerprint,
        actor,
        reason,
        result,
    ):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor,
            "reason": reason,
            "result_snapshot": result,
        }


class _UnitOfWorkFactory:
    def __init__(self):
        self.commits = 0

    def __call__(self):
        return _UnitOfWork(self)


class _UnitOfWork:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        del exception_type, exception, traceback
        return False

    def commit(self):
        self.owner.commits += 1
