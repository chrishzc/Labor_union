"""Historical payroll dates are derived from the adopted end and formal funding."""

from datetime import date
from decimal import Decimal

import pytest

from domains.staff_payables.subsidy_handoff import SubsidyPayableHandoff
from subsystems.payroll.historical_baseline_obligation_sync import _funding_schedule, synchronize_historical_payroll


@pytest.mark.parametrize(
    ("scheme", "subsidy", "existing_due", "expected_due", "expected_portions"),
    [
        ("unknown", 0, None, date(2026, 12, 15), ()),
        ("split", 12000, None, date(2027, 1, 15), (("client", 0), ("subsidy", 12000))),
        ("split", 5000, None, date(2026, 12, 15), (("client", 7000), ("subsidy", 5000))),
        ("direct", 5000, date(2027, 3, 15), date(2027, 3, 15), ()),
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
    assert _funding_schedule(None, "CASE-1", {"actual_end_date": date(2026, 11, 30)}, 12000) == "conflict"


_ORDER = {"status": "歷史訂單－服務完成", "service_days": 5,
          "service_hours_per_day": Decimal("8"), "floor_fee": 0,
          "actual_end_date": date(2026, 11, 30), "staff_payment_due_date": None}
_ASSIGNMENT = {"id": 17, "staff_id": 3, "source_end_date": date(2026, 11, 30),
               "policy_version": "rates-v1", "policy_kind": "citizen", "hourly_rate_ntd": 300}
_UNPAID = {"obligation_identity": "staff-existing:17", "assignment_id": 17, "staff_id": 3,
           "amount_due_ntd": 11000, "effective_amount_due_ntd": 14000, "due_date": None, "status": "open",
           "payout_history_exists": False, "has_formed_due_date": False, "has_positive_installments": False,
           "has_payment": False}


class ReadOnlyConnection:
    def __init__(self, *results):
        self.results = iter(results)
        self.selects = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False

    def execute(self, sql, params):
        assert sql.lstrip().startswith("SELECT")
        self.selects.append((sql, params))

    def fetchone(self):
        return next(self.results)

    def fetchall(self):
        return next(self.results)


@pytest.mark.parametrize("scheme,subsidy", [("unknown", None), ("unknown", 5000), ("waiting", 5000)])
def test_unknown_payment_source_blocks_apply_before_any_write(monkeypatch, scheme, subsidy):
    connection = ReadOnlyConnection(_ORDER, None, (_ASSIGNMENT,), (), (), ())
    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, payroll_candidate_total: SubsidyPayableHandoff(scheme, False, True, subsidy, False),
    )

    result = synchronize_historical_payroll(connection, "CASE-1")

    assert result["action"] == "skipped"
    assert result["reason"] == "historical_payroll_funding_conflict"
    assert "付款來源尚未確認" in result["detail"]


@pytest.mark.parametrize("pending_count,payables,expected_reason", [
    (1, (), "historical_payroll_attribution_pending"),
    (None, (), "historical_payroll_attribution_pending"),
    (None, ({"has_verified_obligation": 1}, {"has_verified_obligation": 0}), "historical_payroll_attribution_pending"),
    (None, ({"has_verified_obligation": 1}, {"has_verified_obligation": 1}), "already_synced"),
])
def test_attribution_requires_current_formal_payables(pending_count, payables, expected_reason):
    connection = ReadOnlyConnection(_ORDER, {"event_id": 41, "pending_count": pending_count}, payables)

    result = synchronize_historical_payroll(connection, "CASE-1")

    assert result["reason"] == expected_reason
    if pending_count:
        assert len(connection.selects) == 2
        assert "原付款證據" in result["detail"]
    else:
        assert connection.selects[-1][1] == ("CASE-1", 41)


@pytest.mark.parametrize("has_payment,has_installments,formed,expected_reason", [
    (False, True, False, "historical_payroll_installment_date_pending"),
    (True, False, False, "historical_payroll_original_payment_preserved"),
    (False, True, True, "already_synced"),
])
def test_existing_payment_evidence_and_installments_are_preserved(has_payment, has_installments, formed, expected_reason):
    original = {**_UNPAID, "has_formed_due_date": formed, "has_positive_installments": has_installments,
                "has_payment": has_payment}
    connection = ReadOnlyConnection(_ORDER, None, (_ASSIGNMENT,), (original,))

    assert synchronize_historical_payroll(connection, "CASE-1")["reason"] == expected_reason


@pytest.mark.parametrize("dry_run", [True, False])
def test_missing_date_uses_effective_amount_without_rewriting_original_amount(monkeypatch, dry_run):
    class RecordingConnection(ReadOnlyConnection):
        def execute(self, sql, params):
            self.selects.append((sql, params))

    existing = (_ORDER, None, (_ASSIGNMENT,), (_UNPAID,), ())
    connection = (
        ReadOnlyConnection(*existing) if dry_run else RecordingConnection(
            *existing, (), {"aggregate_version": 1}, {"obligation_identity": _UNPAID["obligation_identity"]},
        )
    )
    actions = []
    installments = []

    def read_handoff(connection, case_no, *, payroll_candidate_total):
        assert payroll_candidate_total == 14000
        return SubsidyPayableHandoff("split", False, True, 11500, False)

    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff", read_handoff,
    )
    monkeypatch.setattr(
        "subsystems.payroll.rebuild_workflow.PayrollRebuildWorkflow.persist_source_preview",
        lambda self, case_no, preview, **kwargs: actions.extend(preview.actions),
    )
    monkeypatch.setattr(
        "infrastructure.mysql.payroll_installments.establish_confirmed_subsidy_installments",
        lambda cursor, identity, portions: installments.append((identity, portions)),
    )

    assert synchronize_historical_payroll(connection, "CASE-1", dry_run=dry_run) == {
        "action": "updated", "staff_id": 3, "amount_ntd": 14000, "due_date": "2026-12-15",
    }
    if dry_run:
        assert not actions and not installments
        return
    action, = actions
    assert action.obligation_identity == _UNPAID["obligation_identity"]
    assert action.action.value == "replace_unpaid"
    assert (action.before_amount.amount, action.after_amount.amount, action.delta_amount.amount) == (11000, 11000, 0)
    (identity, portions), = installments
    assert identity == _UNPAID["obligation_identity"]
    assert [(part.funding_kind, part.amount) for part in portions] == [("client", 2500), ("subsidy", 11500)]


def test_missing_date_skips_zero_effective_amount_instead_of_using_original_amount():
    original = {**_UNPAID, "effective_amount_due_ntd": 0}
    connection = ReadOnlyConnection(_ORDER, None, (_ASSIGNMENT,), (original,), (), ())

    result = synchronize_historical_payroll(connection, "CASE-1")

    assert result["action"] == "skipped"
    assert result["reason"] == "historical_payroll_nonpositive_amount"
