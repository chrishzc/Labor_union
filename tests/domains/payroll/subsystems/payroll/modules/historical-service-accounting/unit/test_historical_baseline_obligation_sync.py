"""Historical payroll dates are derived from the adopted end and formal funding."""

from datetime import date

import pytest

from domains.staff_payables.subsidy_handoff import SubsidyPayableHandoff
from subsystems.payroll.historical_baseline_obligation_sync import _funding_schedule


@pytest.mark.parametrize(
    ("scheme", "subsidy", "existing_due", "expected_due", "expected_portions"),
    [
        ("unknown", None, None, date(2026, 12, 15), ()),
        ("split", 12000, None, date(2027, 1, 15), (("client", 0), ("subsidy", 12000))),
        ("split", 5000, None, date(2026, 12, 15), (("client", 7000), ("subsidy", 5000))),
        ("unknown", None, date(2027, 3, 15), date(2027, 3, 15), ()),
    ],
)
def test_historical_due_date_preserves_recorded_dates_and_separates_funding(
    monkeypatch, scheme, subsidy, existing_due, expected_due, expected_portions,
):
    handoff = SubsidyPayableHandoff(scheme, False, True, subsidy, subsidy == 12000)
    def read_handoff(connection, case_no, *, payroll_candidate_total):
        assert payroll_candidate_total == 12000
        return handoff

    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        read_handoff,
    )
    due_date, portions = _funding_schedule(
        None, "CASE-1",
        {"actual_end_date": date(2026, 11, 30), "staff_payment_due_date": existing_due},
        12000,
    )
    assert due_date == expected_due
    assert tuple((item.funding_kind, item.amount) for item in portions) == expected_portions
    if portions:
        assert portions[1].due_date == date(2027, 1, 15)


def test_conflicting_historical_funding_blocks_establishment(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, payroll_candidate_total: SubsidyPayableHandoff("split", False, True, 5000, False, staff_subsidy_reason="conflict"),
    )
    assert _funding_schedule(None, "CASE-1", {"actual_end_date": date(2026, 11, 30)}, 12000) is None
