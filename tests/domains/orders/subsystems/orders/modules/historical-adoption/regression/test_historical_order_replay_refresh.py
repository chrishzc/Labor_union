"""Regression coverage for actionable Historical Orders replay refresh."""

from datetime import date
import json

from domains.orders.historical_adoption import HistoricalOrderOutcome, HistoricalOrderSourceStatus
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders import historical_order_workbook_import as module
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionPreview,
    HistoricalOrderAdoptionReceipt,
    HistoricalPairingCandidate,
    HistoricalPairingResolution,
)
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbook,
    HistoricalOrderWorkbookRow,
)


def test_terminal_replay_refreshes_status_actual_start_and_resolvable_staff(
    monkeypatch,
) -> None:
    digest = "a" * 64
    source_identity = f"historical-orders:{digest}:row:2"
    cancelled_row = HistoricalOrderWorkbookRow(
        2,
        source_identity,
        "b" * 64,
        "CASE-1",
        "客戶甲",
        HistoricalOrderSourceStatus.CANCELLED,
        date(2025, 1, 2),
        date(2025, 1, 31),
        (),
        (),
    )
    completed_identity = f"historical-orders:{digest}:row:3"
    completed_row = HistoricalOrderWorkbookRow(
        3,
        completed_identity,
        "e" * 64,
        "CASE-2",
        "客戶乙",
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        date(2025, 2, 2),
        date(2025, 2, 28),
        (
            HistoricalCaregiverSource(
                1,
                "月嫂甲",
                date(2025, 2, 2),
                date(2025, 2, 28),
                True,
                (),
            ),
        ),
        (),
    )
    actual_start_identity = f"historical-orders:{digest}:row:4"
    actual_start_row = HistoricalOrderWorkbookRow(
        4,
        actual_start_identity,
        "f" * 64,
        "CASE-3",
        "客戶丙",
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        date(2025, 3, 3),
        date(2025, 3, 31),
        (),
        (),
    )
    workbook = HistoricalOrderWorkbook(
        digest,
        "c" * 64,
        "歷史訂單",
        (cancelled_row, completed_row, actual_start_row),
    )
    workflow = _Workflow()
    repository = _Repository(digest)
    service = module.HistoricalOrderWorkbookImportService(
        repository,
        workflow,
        _UnitOfWork,
    )
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda _path: workbook)
    supplied = service.preview("historical.xlsx").preview_fingerprint

    receipt = service.apply(
        "historical.xlsx",
        "historical-workbook:key",
        supplied,
        "operator",
        "correlation",
    )

    assert receipt.assignments_created == 1
    assert receipt.replayed_workbook is False
    assert workflow.applied_source_identities[0] == source_identity
    assert workflow.applied_source_identities[1].startswith(source_identity + ":refresh:")
    assert workflow.applied_source_identities[2] == completed_identity
    assert workflow.applied_source_identities[3].startswith(
        completed_identity + ":refresh:"
    )
    assert workflow.applied_source_identities[4] == actual_start_identity
    assert workflow.applied_source_identities[5].startswith(
        actual_start_identity + ":refresh:"
    )


class _Workflow:
    def __init__(self) -> None:
        self.applied_source_identities = []

    def preview(self, row):
        cancelled = row.case_no == "CASE-1"
        actual_start_changed = row.case_no == "CASE-3"
        pairing = HistoricalPairingCandidate(
            1,
            "月**",
            9,
            date(2025, 1, 2),
            date(2025, 1, 31),
            HistoricalPairingResolution.ASSIGNMENT_CANDIDATE,
            (),
        )
        return HistoricalOrderAdoptionPreview(
            row.source_identity,
            row.source_fingerprint,
            HistoricalOrderOutcome.ADOPTED,
            row.case_no,
            0 if cancelled else 1,
            2 if actual_start_changed else 1,
            (
                OrderLifecycleStatus.DISCUSSION.value
                if cancelled
                else OrderLifecycleStatus.COMPLETED.value
            ),
            (
                OrderLifecycleStatus.CANCELLED.value
                if cancelled
                else OrderLifecycleStatus.COMPLETED.value
            ),
            (
                (("actual_start_date", date(2025, 3, 3)),)
                if actual_start_changed
                else ()
            ),
            () if cancelled else (pairing,),
            (),
            PreviewFingerprint("d" * 64),
        )

    def apply(self, request):
        self.applied_source_identities.append(request.row.source_identity)
        refreshed = ":refresh:" in request.row.source_identity
        return HistoricalOrderAdoptionReceipt(
            HistoricalOrderOutcome.ADOPTED,
            request.row.case_no,
            1,
            int(refreshed and request.row.case_no == "CASE-2"),
            None,
            not refreshed,
            request.preview_fingerprint,
        )

    def preview_in_current_unit_of_work(self, row, *, for_update):
        assert for_update is True
        return self.preview(row)

    def apply_in_current_unit_of_work(self, request):
        return self.apply(request)


class _Repository:
    def __init__(self, digest: str) -> None:
        self._digest = digest

    def acquire_lock(self, _key):
        return True

    def release_lock(self, _key):
        return None

    def load_receipt(self, _key):
        return {
            "request_fingerprint": self._digest,
            "result_snapshot": json.dumps(
                {
                    "source_content_digest": self._digest,
                    "source_row_count": 3,
                    "adopted_count": 3,
                    "unmatched_case_count": 0,
                    "review_required_count": 1,
                    "current_conflict_count": 0,
                    "assignments_created": 0,
                    "replayed_rows": 1,
                    "replayed_workbook": False,
                    "status_counts": {
                        "cancelled_0": 1,
                        "completed_1": 2,
                        "discussion_2": 0,
                        "invalid_or_blank": 0,
                    },
                }
            ),
        }


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        return None
