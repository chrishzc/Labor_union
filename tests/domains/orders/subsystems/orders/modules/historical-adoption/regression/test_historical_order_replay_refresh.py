"""Regression coverage for reevaluating a previously imported workbook."""

from datetime import date

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


def test_reimport_reevaluates_every_row_against_current_orders(
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
    repository = _Repository()
    service = module.HistoricalOrderWorkbookImportService(
        repository,
        workflow,
        _UnitOfWork,
    )
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda _path: workbook)

    def apply(operation):
        return service.apply(
            "historical.xlsx",
            f"historical-workbook:{operation}",
            service.preview("historical.xlsx").preview_fingerprint,
            "operator",
            operation,
        )

    unchanged = apply("first")
    assert unchanged.import_counts.as_dict() == {
        "imported_count": 0,
        "duplicate_skipped_count": 3,
        "not_imported_count": 0,
    }
    workflow.cancelled_order_reopened = True
    receipt = apply("second")

    assert receipt.source_content_digest == unchanged.source_content_digest == digest
    assert receipt.assignments_created == 0
    assert receipt.replayed_workbook is False
    assert receipt.import_counts.as_dict() == {
        "imported_count": 1,
        "duplicate_skipped_count": 2,
        "not_imported_count": 0,
    }
    assert workflow.applied_source_identities == [
        source_identity, completed_identity, actual_start_identity,
        source_identity, completed_identity, actual_start_identity,
    ]
    assert receipt.status_counts.as_dict() == {
        "cancelled_0": 1,
        "deposit_paid_1": 2,
        "discussion_2": 0,
        "invalid_or_blank": 0,
    }


class _Workflow:
    def __init__(self) -> None:
        self.applied_source_identities = []
        self.cancelled_order_reopened = False

    def preview(self, row):
        cancelled = row.case_no == "CASE-1"
        current_cancelled_order_status = (
            OrderLifecycleStatus.DISCUSSION
            if self.cancelled_order_reopened
            else OrderLifecycleStatus.CANCELLED
        )
        actual_start_changed = row.case_no == "CASE-3"
        pairing = HistoricalPairingCandidate(
            1,
            "月**",
            9,
            row.actual_start_date,
            row.actual_end_date,
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
                current_cancelled_order_status.value
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
        changed = request.row.case_no == "CASE-1" and self.cancelled_order_reopened
        return HistoricalOrderAdoptionReceipt(
            HistoricalOrderOutcome.ADOPTED,
            request.row.case_no,
            1,
            0,
            None,
            False,
            request.preview_fingerprint,
            unchanged=not changed,
        )

    def preview_in_current_unit_of_work(self, row, *, for_update):
        assert for_update is True
        return self.preview(row)

    def apply_in_current_unit_of_work(self, request):
        return self.apply(request)


class _Repository:
    def acquire_lock(self, _key):
        return True

    def release_lock(self, _key):
        return None

    def find_absent_orders(self, _source_case_nos, *, for_update):
        assert type(for_update) is bool
        return ()

    def cancel_absent_orders(
        self,
        candidates,
        *,
        workbook_key,
        source_content_digest,
        actor,
        correlation_id,
    ):
        del workbook_key, source_content_digest, actor, correlation_id
        assert candidates == ()
        return 0


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        return None
