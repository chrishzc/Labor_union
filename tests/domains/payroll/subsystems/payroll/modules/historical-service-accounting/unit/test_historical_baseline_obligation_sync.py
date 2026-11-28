"""Historical payroll dates are derived from the adopted end and formal funding."""

from datetime import date
from decimal import Decimal

import pytest

from domains.staff_payables.subsidy_handoff import SubsidyPayableHandoff
from subsystems.payroll.historical_baseline_obligation_sync import (
    HistoricalFundingSchedule,
    _funding_schedule,
    synchronize_historical_payroll,
)


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
    schedule = _funding_schedule(
        None, "CASE-1",
        {"actual_end_date": date(2026, 11, 30), "staff_payment_due_date": existing_due},
        12000,
    )
    assert isinstance(schedule, HistoricalFundingSchedule)
    assert schedule.due_date == expected_due
    assert schedule.pending_reason is None
    assert tuple((item.funding_kind, item.amount) for item in schedule.portions) == expected_portions
    if schedule.portions:
        assert schedule.portions[1].due_date == date(2027, 1, 15)


def test_conflicting_historical_funding_leaves_schedule_pending_without_blocking(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, payroll_candidate_total: SubsidyPayableHandoff("split", False, True, 5000, False, staff_subsidy_reason="conflict"),
    )
    schedule = _funding_schedule(None, "CASE-1", {"actual_end_date": date(2026, 11, 30)}, 12000)
    assert schedule == HistoricalFundingSchedule(
        due_date=None,
        portions=(),
        pending_reason="historical_payroll_funding_conflict",
        pending_detail="conflict",
    )


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
            "source_end_date": date(2026, 11, 30), "assignment_valid": True,
            "pairing_evidence_count": 1, **values}


def _availability_root(**values):
    return {**_ORDER, "adoption_receipt_id": 91, "day_event_id": None, **values}


@pytest.mark.parametrize("source_kind,day_event_id,reason", [
    ("duplicate_months", None, "historical_payroll_assignment_source_ambiguous"),
    ("collapsed_duplicate_months", 42, "historical_payroll_assignment_source_ambiguous"),
    ("missing_assignment", None, "historical_payroll_assignment_source_missing"),
    ("invalid_assignment", None, "historical_payroll_assignment_source_missing"),
    ("missing_end", None, "historical_payroll_end_date_missing"),
])
def test_staff_availability_never_estimates_installments_from_unproven_person_end_date(
    source_kind, day_event_id, reason,
):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    source_rows = {
        "duplicate_months": (_availability_source(source_end_date=date(2026, 10, 31)),
                             _availability_source(source_end_date=date(2026, 12, 31))),
        "collapsed_duplicate_months": (_availability_source(source_end_date=None, pairing_evidence_count=2),),
        "missing_assignment": (),
        "invalid_assignment": (_availability_source(assignment_valid=False),),
        "missing_end": (_availability_source(source_end_date=None),),
    }[source_kind]
    original = {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
                "obligation_identity": "staff-existing:17", "due_date": date(2027, 3, 8),
                "expected_ntd": 12000, "has_installments": True, "missing_installment_date": True,
                "missing_client_date": True, "missing_subsidy_date": True}
    root = _availability_root(day_event_id=day_event_id, actual_end_date=date(2027, 1, 31),
                              staff_payment_due_date=date(2027, 5, 9))
    connection = ReadOnlyConnection(root, source_rows, (original,))

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "formal"
    assert result[0].obligation_identities == ("staff-existing:17",)
    assert reason in result[0].pending_reasons
    assert result[0].estimated_self_pay_date is None
    assert result[0].estimated_subsidy_date is None
    assert original["due_date"] == date(2027, 3, 8)
    assert root["staff_payment_due_date"] == date(2027, 5, 9)


@pytest.mark.parametrize("missing_client,missing_subsidy,self_pay,subsidy_date", [
    (False, True, None, "2027-02-15"),
    (True, False, "2027-01-15", None),
])
def test_staff_availability_unique_person_end_estimates_only_the_missing_funding_date(
    missing_client, missing_subsidy, self_pay, subsidy_date,
):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    original = {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
                "obligation_identity": "staff-existing:17", "due_date": date(2027, 3, 8),
                "expected_ntd": 12000, "has_installments": True, "missing_installment_date": True,
                "missing_client_date": missing_client, "missing_subsidy_date": missing_subsidy}
    connection = ReadOnlyConnection(
        _availability_root(actual_end_date=date(2027, 1, 31)),
        (_availability_source(source_end_date=date(2026, 12, 31)),), (original,),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].estimated_self_pay_date == self_pay
    assert result[0].estimated_subsidy_date == subsidy_date
    assert result[0].pending_reasons == ("historical_payroll_installment_date_pending",)
    assert original["due_date"] == date(2027, 3, 8)


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
    assert result[0].pending_reasons == (
        "historical_payroll_due_date_missing", "historical_payroll_funding_source_missing",
    )
    assert result[0].estimated_self_pay_date is None


@pytest.mark.parametrize("obligation_due,recorded_due,expected_recorded", [
    (None, date(2027, 3, 4), "2027-03-04"),
    (date(2027, 4, 8), date(2027, 3, 4), None),
    (None, None, None),
])
def test_staff_availability_reads_recorded_single_payment_date_without_replacing_formal_due(
    obligation_due, recorded_due, expected_recorded,
):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    original = {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
                "obligation_identity": "staff-existing:17", "due_date": obligation_due,
                "has_installments": False, "missing_installment_date": False,
                "missing_client_date": False, "missing_subsidy_date": False}
    connection = ReadOnlyConnection(
        _availability_root(staff_payment_due_date=recorded_due), (_availability_source(),), (original,),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].recorded_due_date == expected_recorded
    assert original["due_date"] == obligation_due
    assert result[0].estimated_self_pay_date is None
    assert result[0].estimated_subsidy_date is None
    assert ("historical_payroll_funding_source_missing" in result[0].pending_reasons) is (
        obligation_due is None and recorded_due is None
    )


@pytest.mark.parametrize("scheme,subsidy,self_pay,subsidy_date", [
    ("split", 0, "2027-01-15", None),
    ("split", 12000, None, "2027-02-15"),
    ("split", 5000, "2027-01-15", "2027-02-15"),
    ("advance", 5000, "2027-01-15", None),
    ("direct", 5000, "2027-01-15", None),
])
def test_staff_availability_estimates_unique_single_payment_from_formal_funding(
    monkeypatch, scheme, subsidy, self_pay, subsidy_date,
):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    calls = []
    def handoff(connection, case_no):
        calls.append(case_no)
        return SubsidyPayableHandoff(scheme, True, True, subsidy, subsidy == 12000, confirmed=True)

    monkeypatch.setattr("infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff", handoff)
    original = {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
                "obligation_identity": "staff-existing:17", "due_date": None, "expected_ntd": 12000,
                "has_installments": False, "missing_installment_date": False,
                "missing_client_date": False, "missing_subsidy_date": False}
    connection = ReadOnlyConnection(
        _availability_root(actual_end_date=date(2026, 12, 31)),
        (_availability_source(source_end_date=date(2026, 12, 31)),), (original,),
    )

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].estimated_self_pay_date == self_pay
    assert result[0].estimated_subsidy_date == subsidy_date
    assert result[0].recorded_due_date is None and original["due_date"] is None
    assert result[0].pending_reasons == ("historical_payroll_due_date_missing",)
    assert calls == ["CASE-1"]
    assert len(connection.selects) == 3


@pytest.mark.parametrize("scheme,subsidy,reason,source_end", [
    ("unknown", 5000, None, date(2026, 12, 31)),
    ("split", None, None, date(2026, 12, 31)),
    ("split", 13000, None, date(2026, 12, 31)),
    ("split", 5000, "formal funding conflict", date(2026, 12, 31)),
    ("split", 5000, None, None),
])
def test_staff_availability_does_not_estimate_incomplete_single_payment_funding(
    monkeypatch, scheme, subsidy, reason, source_end,
):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    calls = []
    def handoff(connection, case_no):
        calls.append(case_no)
        return SubsidyPayableHandoff(scheme, True, True, subsidy, False, staff_subsidy_reason=reason)

    monkeypatch.setattr("infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff", handoff)
    connection = ReadOnlyConnection(_availability_root(actual_end_date=source_end),
        (_availability_source(source_end_date=source_end),), ({
            "assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
            "obligation_identity": "staff-existing:17", "due_date": None, "expected_ntd": 12000,
            "has_installments": False, "missing_installment_date": False,
            "missing_client_date": False, "missing_subsidy_date": False,
        },))

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].estimated_self_pay_date is None and result[0].estimated_subsidy_date is None
    assert "historical_payroll_funding_source_missing" in result[0].pending_reasons
    assert calls == ([] if source_end is None else ["CASE-1"])


def test_staff_availability_does_not_allocate_whole_case_subsidy_to_multiple_people(monkeypatch):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability

    def unexpected_handoff(*args, **kwargs):
        raise AssertionError("whole-case subsidy cannot be allocated to individual payables by this query")
    monkeypatch.setattr("infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff", unexpected_handoff)
    obligation = {"assignment_id": 17, "staff_id": 3, "staff_name": "合成月嫂甲",
                  "obligation_identity": "staff-existing:17", "due_date": None, "expected_ntd": 12000,
                  "has_installments": False, "missing_installment_date": False,
                  "missing_client_date": False, "missing_subsidy_date": False}
    connection = ReadOnlyConnection(_availability_root(),
        (_availability_source(), _availability_source(assignment_id=18, staff_id=4)),
        (obligation, {**obligation, "assignment_id": 18, "staff_id": 4, "obligation_identity": "staff-existing:18"}))

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert all(row.estimated_self_pay_date is None and row.estimated_subsidy_date is None for row in result)
    assert all("historical_payroll_funding_source_missing" in row.pending_reasons for row in result)


def test_subsidy_handoff_does_not_recursively_query_staff_availability(monkeypatch):
    from types import SimpleNamespace
    from infrastructure.mysql.accounting_workspace_repository import query_subsidy_payable_handoff
    from subsystems.finance_import.accounting_workspace import CaseAccounting

    configuration = []
    case = CaseAccounting("CASE-1", "Synthetic", None, None, None, None, 0, (), (), (), ())
    def build(connection, **kwargs):
        configuration.append(kwargs)
        return SimpleNamespace(query=lambda case_no: case)
    monkeypatch.setattr("infrastructure.mysql.accounting_workspace_repository.build_accounting_workspace", build)

    query_subsidy_payable_handoff(ReadOnlyConnection({"status": "歷史訂單－服務完成", "has_customer_subsidy_payable": False}), "CASE-1")

    assert configuration == [{"include_staff_availability": False}]


def test_staff_availability_distinguishes_unestablished_payable_and_missing_rate_per_person(monkeypatch):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability
    from subsystems.payroll import historical_baseline_obligation_sync

    connection = ReadOnlyConnection(
        _availability_root(day_event_id=23),
        (_availability_source(), _availability_source(assignment_id=18, staff_id=4,
                                                     staff_name="合成月嫂乙", hourly_rate_ntd=None)),
        (),
    )
    def preview(connection_arg, case_no, *, dry_run=False):
        assert connection_arg is connection and case_no == "CASE-1" and dry_run
        return {"action": "created", "items": [
            {"action": "created", "assignment_id": 17, "staff_id": 3, "amount_ntd": 12000},
            {"action": "skipped", "assignment_id": 18, "staff_id": 4, "reason": "payroll_rate_policy_not_found"},
        ]}
    monkeypatch.setattr(historical_baseline_obligation_sync, "synchronize_historical_payroll", preview)

    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert result[0].status == "not_established"
    assert result[0].estimated_amount_ntd == 12000
    assert not result[0].pending_reasons
    assert result[1].status == "needs_review"
    assert result[1].pending_reasons == ("payroll_rate_policy_not_found",)
    assert result[1].estimated_amount_ntd is None
    assert not result[0].obligation_identities


def test_staff_availability_does_not_distribute_whole_case_service_between_ambiguous_assignments(monkeypatch):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability
    from subsystems.payroll import historical_baseline_obligation_sync

    connection = ReadOnlyConnection(
        _availability_root(),
        (_availability_source(), _availability_source(assignment_id=18, staff_id=4)),
        (),
    )

    calls = []

    def preview(connection_arg, case_no, *, dry_run=False):
        calls.append((connection_arg, case_no, dry_run))
        return {"action": "skipped", "items": [
            {"action": "skipped", "assignment_id": 17, "staff_id": 3, "reason": "historical_payroll_service_basis_missing"},
            {"action": "skipped", "assignment_id": 18, "staff_id": 4, "reason": "historical_payroll_service_basis_missing"},
        ]}

    monkeypatch.setattr(historical_baseline_obligation_sync, "synchronize_historical_payroll", preview)
    result = query_case_staff_accounting_availability(connection, "CASE-1")

    assert calls == [(connection, "CASE-1", True)]
    assert len(result) == 2
    assert all(row.status == "needs_review" for row in result)
    assert all(row.pending_reasons == ("historical_payroll_service_basis_missing",) for row in result)


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


@pytest.mark.parametrize("status", ["歷史訂單－服務完成", "歷史訂單－服務中", "歷史訂單－帳務完成"])
def test_staff_availability_keeps_missing_end_date_distinct_from_missing_service_and_rates(monkeypatch, status):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting_availability
    from subsystems.payroll import historical_baseline_obligation_sync

    connection = ReadOnlyConnection(
        _availability_root(status=status, actual_end_date=None),
        (_availability_source(service_days=20, service_hours=Decimal("160"), source_end_date=None),), (),
    )
    calls = []

    def preview(connection_arg, case_no, *, dry_run=False):
        calls.append((connection_arg, case_no, dry_run))
        return {"action": "created", "assignment_id": 17, "staff_id": 3, "amount_ntd": 48000,
                "pending_reason": "historical_payroll_end_date_missing"}

    monkeypatch.setattr(historical_baseline_obligation_sync, "synchronize_historical_payroll", preview)
    result = query_case_staff_accounting_availability(connection, "CASE-1")

    if status == "歷史訂單－服務完成":
        assert calls == [(connection, "CASE-1", True)]
        assert result[0].status == "not_established"
        assert result[0].estimated_amount_ntd == 48000
        assert result[0].pending_reasons == ("historical_payroll_end_date_missing",)
    else:
        assert calls == []
        assert result[0].status == "needs_review"
        assert result[0].estimated_amount_ntd is None
        expected = ("historical_service_not_completed" if status == "歷史訂單－服務中"
                    else "historical_payroll_settled_source_required")
        assert result[0].pending_reasons == (expected,)
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
def test_unknown_payment_source_establishes_payable_without_due_date_or_installments(monkeypatch, scheme, subsidy):
    class RecordingConnection(ReadOnlyConnection):
        def execute(self, sql, params):
            self.selects.append((sql, params))

    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, payroll_candidate_total: SubsidyPayableHandoff(scheme, False, True, subsidy, False),
    )
    dry_connection = ReadOnlyConnection(_ORDER, None, (_ASSIGNMENT,), (), ())
    dry_result = synchronize_historical_payroll(dry_connection, "CASE-1", dry_run=True)
    assert dry_result["action"] == "created"
    assert dry_result["assignment_id"] == 17
    assert dry_result["staff_id"] == 3
    assert dry_result["obligation_identity"] == "staff-obligation:assignment:17"
    assert dry_result["amount_ntd"] == 12000
    assert dry_result["due_date"] is None
    assert dry_result["payment_arrangement_pending"] is True
    assert dry_result["pending_reason"] == "historical_payroll_funding_pending"
    assert "補助流向" in dry_result["detail"]

    actions = []
    installments = []
    monkeypatch.setattr(
        "subsystems.payroll.rebuild_workflow.PayrollRebuildWorkflow.persist_source_preview",
        lambda self, case_no, preview, **kwargs: actions.extend(preview.actions),
    )
    monkeypatch.setattr(
        "infrastructure.mysql.payroll_installments.establish_confirmed_subsidy_installments",
        lambda cursor, identity, portions: installments.append((identity, portions)),
    )
    apply_connection = RecordingConnection(
        _ORDER, None, (_ASSIGNMENT,), (), (), (), {"aggregate_version": 0},
    )
    created = synchronize_historical_payroll(apply_connection, "CASE-1")
    assert created == dry_result
    action, = actions
    assert action.action.value == "create"
    assert action.after_amount.amount == 12000
    assert action.due_date is None
    assert not installments
    assert all("UPDATE orders SET staff_payment_due_date" not in sql for sql, _ in apply_connection.selects)

    established_undated = {
        **_UNPAID, "obligation_identity": "staff-obligation:assignment:17",
        "amount_due_ntd": 12000, "effective_amount_due_ntd": 12000,
    }
    rerun_connection = ReadOnlyConnection(_ORDER, None, (_ASSIGNMENT,), (established_undated,), (), ())
    rerun = synchronize_historical_payroll(rerun_connection, "CASE-1")
    assert rerun["action"] == "skipped"
    assert rerun["reason"] == "already_synced"
    assert rerun["payment_arrangement_pending"] is True
    assert {field: rerun[field] for field in (
        "assignment_id", "staff_id", "obligation_identity", "amount_ntd", "due_date",
    )} == {field: created[field] for field in (
        "assignment_id", "staff_id", "obligation_identity", "amount_ntd", "due_date",
    )}
    assert len(actions) == 1


@pytest.mark.parametrize("case_end", [None, date(2026, 11, 30)])
def test_missing_person_end_date_establishes_payable_without_fabricating_due_date(monkeypatch, case_end):
    class RecordingConnection(ReadOnlyConnection):
        def execute(self, sql, params):
            self.selects.append((sql, params))

    no_end_order = {**_ORDER, "actual_end_date": case_end}
    no_end_assignment = {**_ASSIGNMENT, "source_end_date": None}
    actions = []
    monkeypatch.setattr(
        "subsystems.payroll.rebuild_workflow.PayrollRebuildWorkflow.persist_source_preview",
        lambda self, case_no, preview, **kwargs: actions.extend(preview.actions),
    )
    connection = RecordingConnection(
        no_end_order, None, (no_end_assignment,), (), (), (), {"aggregate_version": 0},
    )
    created = synchronize_historical_payroll(connection, "CASE-1")
    assert created["action"] == "created"
    assert created["amount_ntd"] == 12000
    assert created["due_date"] is None
    assert created["pending_reason"] == "historical_payroll_end_date_missing"
    assert actions[0].due_date is None
    assert all("UPDATE orders SET staff_payment_due_date" not in sql for sql, _ in connection.selects)


@pytest.mark.parametrize(("days", "rate", "blocker"), [
    (0, 300, "historical_payroll_service_basis_missing"),
    (5, None, "payroll_rate_policy_not_found"),
    (5, 450, "payroll_rate_policy_not_found"),
])
def test_multi_caregiver_sync_creates_only_verifiable_assignment_without_copying_case_totals(monkeypatch, days, rate, blocker):
    class RecordingConnection(ReadOnlyConnection):
        def execute(self, sql, params):
            self.selects.append((sql, params))

    case_order = {**_ORDER, "service_days": 20}
    caregiver_a = {**_ASSIGNMENT, "id": 17, "staff_id": 3, "schedule_service_days": 8, "hourly_rate_ntd": 300}
    caregiver_b = {**_ASSIGNMENT, "id": 18, "staff_id": 4, "schedule_service_days": days, "hourly_rate_ntd": rate}
    caregiver_c = {**_ASSIGNMENT, "id": 19, "staff_id": 5, "schedule_service_days": 6, "hourly_rate_ntd": 300}
    paid_c = {
        "obligation_identity": "staff-obligation:assignment:19", "assignment_id": 19, "staff_id": 5,
        "amount_due_ntd": 14400, "effective_amount_due_ntd": 14400, "due_date": date(2026, 12, 15),
        "status": "settled", "payout_history_exists": True, "has_formed_due_date": True,
        "has_positive_installments": False, "has_payment": True,
    }
    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, payroll_candidate_total: SubsidyPayableHandoff("unknown", False, True, 12000, False),
    )
    actions = []
    monkeypatch.setattr(
        "subsystems.payroll.rebuild_workflow.PayrollRebuildWorkflow.persist_source_preview",
        lambda self, case_no, preview, **kwargs: actions.extend(preview.actions),
    )

    dry = synchronize_historical_payroll(
        ReadOnlyConnection(case_order, None, (caregiver_a, caregiver_b, caregiver_c), (paid_c,), ()),
        "CASE-MULTI",
        dry_run=True,
    )
    assert dry["action"] == "created"
    assert dry["reason"] == blocker
    assert "其餘仍待查核" in dry["detail"]
    assert [(item["staff_id"], item["action"], item.get("amount_ntd"), item.get("reason")) for item in dry["items"]] == [
        (3, "created", 19200, None),
        (4, "skipped", None, blocker),
        (5, "skipped", 14400, "already_synced"),
    ]
    assert dry["items"][2]["obligation_identity"] == paid_c["obligation_identity"]
    assert dry["items"][2]["due_date"] == "2026-12-15"
    assert not actions

    applied = synchronize_historical_payroll(
        RecordingConnection(
            case_order, None, (caregiver_a, caregiver_b, caregiver_c), (paid_c,), (), (), {"aggregate_version": 0},
        ),
        "CASE-MULTI",
    )
    assert applied == dry
    assert len(actions) == 1
    assert actions[0].assignment_identity == "assignment:17"
    assert actions[0].after_amount.amount == 19200
    assert actions[0].due_date is None


def test_multi_caregiver_sync_allocates_prorated_floor_fee_without_a_probe_rate(monkeypatch):
    order = {**_ORDER, "service_days": 20, "floor_fee": 3000}
    caregiver_a = {**_ASSIGNMENT, "id": 17, "staff_id": 3, "schedule_service_days": 8}
    caregiver_b = {**_ASSIGNMENT, "id": 18, "staff_id": 4, "schedule_service_days": 4}
    monkeypatch.setattr(
        "infrastructure.mysql.accounting_workspace_repository.query_subsidy_payable_handoff",
        lambda *_, complete_payroll_total: SubsidyPayableHandoff("unknown", False, True, 12000, False),
    )

    result = synchronize_historical_payroll(
        ReadOnlyConnection(order, None, (caregiver_a, caregiver_b), (), ()),
        "CASE-MULTI-FLOOR", dry_run=True,
    )

    assert result["action"] == "created"
    assert [(item["assignment_id"], item["amount_ntd"], item["due_date"]) for item in result["items"]] == [
        (17, 20400, None),
        (18, 10200, None),
    ]


def test_malformed_service_hours_are_reported_without_writing_payroll():
    order = {**_ORDER, "service_hours_per_day": Decimal("8.1")}
    connection = ReadOnlyConnection(order, None, (_ASSIGNMENT,), ())

    result = synchronize_historical_payroll(connection, "CASE-1")

    assert result["action"] == "skipped"
    assert result["reason"] == "historical_payroll_service_basis_missing"


_ATTRIBUTED_PAYABLE = {"assignment_id": 17, "staff_id": 3, "obligation_identity": "attributed-17"}
_ATTRIBUTED_PERSON_MISSING_PAYABLE = {"assignment_id": 18, "staff_id": 4, "obligation_identity": None}


@pytest.mark.parametrize("pending_count,payables,expected_reason", [
    (1, (), "historical_payroll_attribution_pending"),
    (None, (), "historical_payroll_attribution_pending"),
    (None, (_ATTRIBUTED_PAYABLE, _ATTRIBUTED_PERSON_MISSING_PAYABLE), "historical_payroll_attribution_pending"),
    (None, (_ATTRIBUTED_PAYABLE,), "already_synced"),
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
        assert [(item["assignment_id"], item["staff_id"], item["obligation_identity"], item["reason"])
                for item in result["items"]] == [
            (row["assignment_id"], row["staff_id"], row["obligation_identity"],
             "already_synced" if row["obligation_identity"] else "historical_payroll_attribution_pending")
            for row in payables
        ]


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
        "action": "updated", "assignment_id": 17, "staff_id": 3, "obligation_identity": _UNPAID["obligation_identity"],
        "amount_ntd": 14000, "due_date": "2026-12-15",
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
