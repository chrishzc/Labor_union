from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from domains.orders.historical_adoption import (
    HistoricalOrderCurrentFacts,
    HistoricalOrderSourceStatus,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionWorkflow,
    HistoricalPairingResolution,
)


class _Repository:
    def load_order(self, case_no, client_name, *, for_update):
        del for_update
        assert (case_no, client_name) == ("CASE-1", "客戶甲")
        return HistoricalOrderCurrentFacts(
            "CASE-1",
            "客戶甲",
            OrderLifecycleStatus.DISCUSSION,
            3,
            date(2026, 8, 6),
            None,
            None,
        )

    def resolve_staff(self, name, *, for_update):
        del for_update
        return (11,) if name == "月嫂甲" else ()

    def active_assignments(self, case_no, *, for_update):
        del case_no, for_update
        return ()

    def find_receipt(self, key, source_identity):
        del key, source_identity
        return None


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Writer:
    def append_completed_assignments(self, case_no, assignments):
        del case_no, assignments
        return ()


def test_deposit_paid_with_distinct_actual_start_builds_service_assignment_candidate():
    caregiver = SimpleNamespace(
        ordinal=1,
        name="月嫂甲",
        start_date=date(2026, 8, 7),
        end_date=date(2026, 9, 7),
        has_individual_interval=True,
        issue_codes=(),
    )
    row = SimpleNamespace(
        case_no="CASE-1",
        client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=date(2026, 8, 7),
        actual_end_date=date(2026, 9, 7),
        issue_codes=(),
        caregivers=(caregiver,),
        source_identity="historical-orders:test:row:1",
        source_fingerprint="f" * 64,
    )

    preview = HistoricalOrderAdoptionWorkflow(
        _Repository(), _UnitOfWork, _Writer()
    ).preview(row)

    assert preview.after_status == OrderLifecycleStatus.ESTABLISHED.value
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
    assert preview.issue_codes == ()
