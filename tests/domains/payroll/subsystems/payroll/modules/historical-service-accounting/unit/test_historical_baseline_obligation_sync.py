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


def _availability_source(**values):
    return {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
            "service_days": 5, "service_hours": Decimal("40"), "hourly_rate_ntd": 300,
            "source_end_date": date(2026, 11, 30), "assignment_valid": True, **values}


def _availability_root(**values):
    return {**_ORDER, "adoption_receipt_id": 91, "day_event_id": None, **values}


def test_staff_availability_keeps_formal_payable_when_service_basis_is_missing():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(
        _availability_root(service_days=None, service_hours_per_day=None),
        (_availability_source(service_days=None, service_hours=None, hourly_rate_ntd=None),),
        ({"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
          "obligation_identity": "staff-existing:17", "due_date": None,
          "has_installments": False, "missing_installment_date": False,
          "missing_client_date": False, "missing_subsidy_date": False},),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert len(result) == 1
    assert result[0].status == "formal"
    assert result[0].obligation_identities == ("staff-existing:17",)
    assert result[0].pending_reasons == ("historical_payroll_due_date_missing",)
    assert result[0].estimated_self_pay_date is None


def test_staff_availability_distinguishes_unestablished_payable_and_missing_rate_per_person():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(
        _availability_root(day_event_id=23),
        (_availability_source(), _availability_source(assignment_id=18, staff_id=4,
                                                     staff_name="合成月嫂乙", hourly_rate_ntd=None)),
        (),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "not_established"
    assert result[0].pending_reasons == ("historical_payroll_obligation_not_established",)
    assert result[1].status == "needs_review"
    assert result[1].pending_reasons == ("payroll_rate_policy_not_found",)
    assert not result[0].obligation_identities


def test_staff_availability_does_not_distribute_whole_case_service_between_ambiguous_assignments():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(
        _availability_root(),
        (_availability_source(), _availability_source(assignment_id=18, staff_id=4)),
        (),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert len(result) == 2
    assert all(row.status == "needs_review" for row in result)
    assert all("historical_payroll_service_attribution_missing" in row.pending_reasons for row in result)


def test_staff_availability_preserves_reopened_formal_dates_and_estimates_only_missing_funding_dates():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    root = _availability_root(status="服務中", actual_end_date=date(2026, 12, 31))
    connection = ReadOnlyConnection(root, (_availability_source(source_end_date=date(2026, 12, 31)),), (
        {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
         "obligation_identity": "staff-existing:17", "due_date": date(2027, 4, 8),
         "has_installments": True, "missing_installment_date": True,
         "missing_client_date": True, "missing_subsidy_date": True},
    ))

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "formal"
    assert result[0].pending_reasons == ("historical_payroll_installment_date_pending",)
    assert result[0].estimated_self_pay_date == "2027-01-15"
    assert result[0].estimated_subsidy_date == "2027-02-15"
    assert connection.selects[0][1] == ("CASE-1",)


def test_staff_availability_retains_existing_payables_when_original_assignment_is_missing():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(_availability_root(), (), (
        {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
         "obligation_identity": "staff-existing:17", "due_date": date(2027, 4, 8),
         "has_installments": False, "missing_installment_date": False,
         "missing_client_date": False, "missing_subsidy_date": False},
    ))

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "formal"
    assert result[0].obligation_identities == ("staff-existing:17",)
    assert result[0].pending_reasons == ("historical_payroll_assignment_source_missing",)


def test_staff_availability_keeps_missing_end_date_distinct_from_missing_service_and_rates():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(
        _availability_root(actual_end_date=None), (_availability_source(source_end_date=None),), (),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "needs_review"
    assert result[0].pending_reasons == ("historical_payroll_end_date_missing",)
    assert result[0].estimated_self_pay_date is None
    assert result[0].estimated_subsidy_date is None


def test_staff_availability_does_not_pick_a_duplicate_assignment_source():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(_availability_root(), (
        _availability_source(hourly_rate_ntd=300), _availability_source(hourly_rate_ntd=450),
    ), ())

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert len(result) == 1
    assert result[0].status == "needs_review"
    assert "historical_payroll_assignment_source_ambiguous" in result[0].pending_reasons
    assert not result[0].obligation_identities


def test_staff_availability_does_not_require_historical_evidence_for_normal_orders():
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    connection = ReadOnlyConnection(_availability_root(status="服務中", adoption_receipt_id=None))

    assert query_case_staff_accounting_availability(connection, "CASE-1") == ()
    assert len(connection.selects) == 1


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
