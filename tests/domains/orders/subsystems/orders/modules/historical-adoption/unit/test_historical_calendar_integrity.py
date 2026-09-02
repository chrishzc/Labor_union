from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from domains.orders.historical_adoption import (
    HistoricalOrderCurrentFacts,
    HistoricalOrderOutcome,
    HistoricalOrderSourceStatus,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
    HistoricalPairingResolution,
)
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
)


_BUSINESS_DATE = date(2026, 9, 1)
_START = date(2026, 8, 1)
_END = date(2026, 8, 31)


def test_service_history_with_missing_staff_is_review_required_and_zero_order_transition():
    row = _row(caregiver_name=None, start=_START, end=_END)
    repository = _Repository()
    writer = _Writer()
    workflow = _workflow(repository, writer)

    preview = workflow.preview(row)

    assert preview.outcome is HistoricalOrderOutcome.REVIEW_REQUIRED
    assert preview.before_status == OrderLifecycleStatus.DISCUSSION.value
    assert preview.after_status == OrderLifecycleStatus.DISCUSSION.value
    assert preview.expected_version == preview.resulting_version == 3
    assert preview.date_patch == ()
    assert "historical_calendar_staff_missing" in preview.issue_codes
    assert "historical_calendar_completed_assignment_missing" in preview.issue_codes

    receipt = workflow.apply(
        HistoricalOrderAdoptionRequest(
            row=row,
            preview_fingerprint=preview.fingerprint,
            idempotency_key="issue-113:missing-staff",
            actor="test-operator",
            reason="verify historical calendar integrity",
            correlation_id="issue-113:missing-staff:correlation",
        )
    )

    assert receipt.outcome is HistoricalOrderOutcome.REVIEW_REQUIRED
    assert writer.calls == []
    assert repository.persisted[0][1].outcome is HistoricalOrderOutcome.REVIEW_REQUIRED
    assert repository.persisted[0][2] == ()


def test_service_history_with_missing_valid_interval_is_review_required():
    row = _row(caregiver_name="月嫂甲", start=_START, end=None)

    preview = _workflow(_Repository(), _Writer()).preview(row)

    assert preview.outcome is HistoricalOrderOutcome.REVIEW_REQUIRED
    assert "historical_calendar_valid_dates_missing" in preview.issue_codes
    assert "historical_calendar_completed_assignment_missing" in preview.issue_codes
    assert "historical_calendar_staff_missing" not in preview.issue_codes


def test_complete_service_history_builds_completed_assignment_before_historical_transition():
    row = _row(caregiver_name="月嫂甲", start=_START, end=_END)
    repository = _Repository()
    writer = _Writer()
    workflow = _workflow(repository, writer)

    preview = workflow.preview(row)

    assert preview.outcome is HistoricalOrderOutcome.ADOPTED
    assert preview.after_status == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE

    receipt = workflow.apply(
        HistoricalOrderAdoptionRequest(
            row=row,
            preview_fingerprint=preview.fingerprint,
            idempotency_key="issue-113:complete",
            actor="test-operator",
            reason="verify historical calendar integrity",
            correlation_id="issue-113:complete:correlation",
        )
    )

    assert receipt.outcome is HistoricalOrderOutcome.ADOPTED
    assert writer.calls == [("CASE-1", ((11, _START, _END),))]
    assert repository.persisted[0][2] == (91,)


def test_existing_completed_historical_assignment_is_reused_without_generation_requirement():
    row = _row(caregiver_name="月嫂甲", start=_START, end=_END)
    repository = _Repository(
        active_assignments=(
            {
                "id": 77,
                "staff_id": 11,
                "status": "completed",
                "assigned_start_date": _START,
                "assigned_end_date": _END,
                "generation_id": None,
            },
        )
    )

    preview = _workflow(repository, _Writer()).preview(row)

    assert preview.outcome is HistoricalOrderOutcome.ADOPTED
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_REUSED
    assert preview.pairings[0].assignment_id == 77


def test_historical_unserved_remains_non_calendar_path_without_staff_or_assignment():
    row = _row(caregiver_name=None, start=None, end=None)

    preview = _workflow(_Repository(), _Writer()).preview(row)

    assert preview.outcome is HistoricalOrderOutcome.ADOPTED
    assert preview.after_status == OrderLifecycleStatus.HISTORICAL_UNSERVED.value
    assert "historical_calendar_completed_assignment_missing" not in preview.issue_codes


def _row(*, caregiver_name, start, end):
    return HistoricalOrderWorkbookRow(
        source_row=2,
        source_identity="historical-orders:test:row:2",
        source_fingerprint="f" * 64,
        case_no="CASE-1",
        client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=start,
        actual_end_date=end,
        caregivers=(
            HistoricalCaregiverSource(
                ordinal=1,
                name=caregiver_name,
                start_date=start,
                end_date=end,
                has_individual_interval=False,
                issue_codes=(),
            ),
        ),
        issue_codes=(),
    )


def _workflow(repository, writer):
    return HistoricalOrderAdoptionWorkflow(
        repository,
        _UnitOfWork,
        writer,
        clock=SimpleNamespace(today=lambda: _BUSINESS_DATE),
    )


class _Repository:
    def __init__(self, *, active_assignments=()):
        self._active_assignments = tuple(active_assignments)
        self.persisted = []

    def load_order(self, case_no, client_name, *, for_update):
        assert case_no == "CASE-1"
        assert client_name == "客戶甲"
        del for_update
        return HistoricalOrderCurrentFacts(
            case_no="CASE-1",
            client_name="客戶甲",
            status=OrderLifecycleStatus.DISCUSSION,
            lifecycle_version=3,
            planned_start_date=None,
            actual_start_date=None,
            actual_end_date=None,
        )

    def resolve_staff(self, name, *, for_update):
        del for_update
        return (11,) if name == "月嫂甲" else ()

    def active_assignments(self, case_no, *, for_update):
        assert case_no == "CASE-1"
        del for_update
        return self._active_assignments

    def find_receipt(self, key, source_identity):
        del key, source_identity
        return None

    def persist(self, request, preview, assignment_ids):
        self.persisted.append((request, preview, assignment_ids))
        return SimpleNamespace(
            outcome=preview.outcome,
            case_no=preview.case_no,
            resulting_version=preview.resulting_version,
            assignment_count=len(assignment_ids),
            review_identity=(
                "historical-order-review:test"
                if preview.outcome is HistoricalOrderOutcome.REVIEW_REQUIRED
                else None
            ),
            replayed=False,
            preview_fingerprint=preview.fingerprint,
        )


class _Writer:
    def __init__(self):
        self.calls = []

    def append_completed_assignments(self, case_no, assignments):
        self.calls.append((case_no, assignments))
        return tuple(91 + index for index, _ in enumerate(assignments))


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        del exception_type, exception, traceback
        return False

    def commit(self):
        return None
