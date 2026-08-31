from datetime import date, datetime, timezone

import pytest

from domains.payroll.late_obligation import (
    LateObligationDisposition,
    LatePayrollObligationFacts,
    LatePayrollObligationIntent,
    build_late_payroll_obligation_candidate,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.payroll.late_obligation_workflow import (
    LatePayrollObligationApplyRequest,
    LatePayrollObligationWorkflow,
)


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _facts(*, current=1000, paid=0, payroll_version=4, obligation_version=2, corrected=1000):
    return LatePayrollObligationFacts(
        "CASE-1", "obligation:1", "staff-obligation-event:7", 8, 17,
        MoneyNTD(current), MoneyNTD(corrected), MoneyNTD(paid), payroll_version,
        obligation_version, date(2026, 8, 1), NOW, True,
    )


def _intent(corrected):
    return LatePayrollObligationIntent(
        "CASE-1", "obligation:1", "staff-obligation-event:7", MoneyNTD(corrected)
    )


def test_late_delta_branches_are_mutually_exclusive_and_source_bound():
    increase = build_late_payroll_obligation_candidate(_facts(corrected=1200, paid=1500), _intent(1200))
    reduction = build_late_payroll_obligation_candidate(_facts(corrected=700), _intent(700))
    paid = build_late_payroll_obligation_candidate(_facts(corrected=700, paid=1000), _intent(700))
    no_change = build_late_payroll_obligation_candidate(_facts(paid=1500), _intent(1000))

    assert increase.disposition is LateObligationDisposition.INCREASE_OBLIGATION
    assert increase.delta_amount.amount == 200
    assert increase.recovery_amount.amount == 0
    assert reduction.disposition is LateObligationDisposition.REDUCE_UNPAID_OBLIGATION
    assert reduction.recovery_amount.amount == 0
    assert paid.disposition is LateObligationDisposition.CORRECT_PAID_OBLIGATION
    assert paid.recovery_amount.amount == 300
    assert no_change.disposition is LateObligationDisposition.REVIEWED_NO_CHANGE
    assert no_change.recovery_amount.amount == 0


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.persisted = []
        self.receipt = None

    def load(self, intent, *, for_update):
        return self.facts

    def find_receipt(self, key):
        return self.receipt

    def persist_late_obligation(self, request, preview, receipt, command_fingerprint):
        self.persisted.append((request, preview, receipt, command_fingerprint))
        self.facts = LatePayrollObligationFacts(
            self.facts.case_no, self.facts.obligation_identity, self.facts.source_event_identity,
            self.facts.assignment_id, self.facts.staff_id, preview.candidate.corrected_amount,
            preview.candidate.corrected_amount, preview.candidate.actual_paid_amount,
            preview.payroll_version + 1, preview.obligation_version + 1, self.facts.due_date,
            self.facts.source_event_at, True,
        )

    def readback_late_obligation(self, intent):
        return self.facts


class _RecoveryPort:
    def __init__(self):
        self.candidates = []

    def create_from_payroll_correction(self, *, candidate, request):
        self.candidates.append(candidate)


def _request(preview, *, key="payout002-1", version=4, obligation_version=2):
    return LatePayrollObligationApplyRequest(
        preview.candidate and _intent(preview.candidate.corrected_amount.amount),
        ExpectedVersion(version), ExpectedVersion(obligation_version), preview.fingerprint,
        IdempotencyKey(key), ActorContext("admin"), "Reviewed late Payroll source.",
        CorrelationId("payout002-test"),
    )


def test_workflow_requires_fresh_versions_and_returns_complete_readback():
    repository = _Repository(_facts(corrected=1200))
    unit = _UnitOfWork()
    workflow = LatePayrollObligationWorkflow(repository, lambda: unit)
    preview = workflow.preview(_intent(1200), CorrelationId("preview"))

    receipt = workflow.apply(_request(preview))

    assert receipt.disposition == "increase_obligation"
    assert receipt.delta_amount_ntd == 200
    assert receipt.payroll_version == 5
    assert unit.committed is True
    assert len(repository.persisted) == 1


def test_paid_reduction_needs_staff_payables_recovery_port():
    repository = _Repository(_facts(corrected=700, paid=1000))
    workflow = LatePayrollObligationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent(700), CorrelationId("preview"))

    with pytest.raises(Exception) as raised:
        workflow.apply(_request(preview))

    assert raised.value.error.code == "staff_overpayment_recovery_unavailable"
    assert repository.persisted == []


@pytest.mark.parametrize(
    ("current", "corrected", "paid", "disposition", "recovery"),
    (
        (1000, 700, 0, "reduce_unpaid_obligation", 0),
        (1000, 1000, 0, "reviewed_no_change", 0),
        (1000, 700, 1000, "correct_paid_obligation", 300),
    ),
)
def test_apply_reaches_terminal_readback_for_each_non_increase_branch(
    current, corrected, paid, disposition, recovery
):
    repository = _Repository(_facts(current=current, paid=paid, corrected=corrected))
    recovery_port = _RecoveryPort()
    workflow = LatePayrollObligationWorkflow(repository, _UnitOfWork, recovery_port)
    preview = workflow.preview(_intent(corrected), CorrelationId("preview"))

    receipt = workflow.apply(_request(preview, key=f"payout002-{disposition}"))

    assert receipt.disposition == disposition
    assert receipt.recovery_amount_ntd == recovery
    assert len(recovery_port.candidates) == (1 if recovery else 0)


def test_apply_replays_same_command_without_second_persistence():
    repository = _Repository(_facts(corrected=1200))
    workflow = LatePayrollObligationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent(1200), CorrelationId("preview"))
    request = _request(preview, key="payout002-replay")
    receipt = workflow.apply(request)
    from subsystems.payroll.late_obligation_workflow import StoredLatePayrollObligationReceipt, _command_fingerprint

    repository.receipt = StoredLatePayrollObligationReceipt(_command_fingerprint(request), receipt)
    repository.persisted.clear()

    assert workflow.apply(request) == receipt
    assert repository.persisted == []


def test_recovery_creation_schema_boundary_is_reported_without_cross_domain_write():
    from infrastructure.mysql.staff_overpayment_recovery_from_payroll_adapter import (
        MySqlStaffOverpaymentRecoveryFromPayrollAdapter,
    )

    class _BoundaryApplication:
        def create_from_payroll_correction(self, _request):
            raise RuntimeError(
                "BOUNDARY_REQUIRED_STAFF_OVERPAYMENT_RECOVERY_SCHEMA_PAYROLL_CORRECTION_IDENTITY"
            )

    repository = _Repository(_facts(corrected=700, paid=1000))
    workflow = LatePayrollObligationWorkflow(
        repository, _UnitOfWork,
        MySqlStaffOverpaymentRecoveryFromPayrollAdapter(object(), application=_BoundaryApplication()),
    )
    preview = workflow.preview(_intent(700), CorrelationId("preview"))

    with pytest.raises(Exception) as raised:
        workflow.apply(_request(preview, key="payout002-recovery-boundary"))

    assert raised.value.error.code == "BOUNDARY_REQUIRED_STAFF_OVERPAYMENT_RECOVERY_SCHEMA_PAYROLL_CORRECTION_IDENTITY"
    assert repository.persisted == []


def test_staff_adapter_composes_exact_payroll_correction_source_into_owner_command():
    from infrastructure.mysql.staff_overpayment_recovery_from_payroll_adapter import (
        MySqlStaffOverpaymentRecoveryFromPayrollAdapter,
    )

    class _Application:
        def __init__(self):
            self.requests = []

        def create_from_payroll_correction(self, request):
            self.requests.append(request)

    application = _Application()
    adapter = MySqlStaffOverpaymentRecoveryFromPayrollAdapter(
        object(), application=application,
    )
    repository = _Repository(_facts(corrected=700, paid=1000))
    workflow = LatePayrollObligationWorkflow(repository, _UnitOfWork, adapter)
    preview = workflow.preview(_intent(700), CorrelationId("preview"))
    workflow.apply(_request(preview, key="payout002-adapter-source"))

    source = application.requests[0].source
    assert source.correction_identity == preview.candidate.correction_identity
    assert source.obligation_identity == preview.candidate.obligation_identity
    assert source.amount.amount == 300


@pytest.mark.parametrize(
    ("current", "corrected", "paid"),
    ((1000, 1200, 0), (1000, 700, 0), (1000, 700, 1000), (1000, 1000, 0)),
)
def test_mysql_repository_persists_each_disposition_without_receivable_direction(
    current, corrected, paid
):
    from infrastructure.mysql.payroll_late_obligation_repository import (
        MySqlPayrollLateObligationRepository,
    )
    from subsystems.payroll.late_obligation_workflow import _command_fingerprint, _receipt

    class _Cursor:
        def __init__(self):
            self.statements = []
            self.lastrowid = 41
            self.rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=()):
            self.statements.append(statement)

    class _Connection:
        def __init__(self):
            self.cursor_value = _Cursor()

        def cursor(self):
            return self.cursor_value

    source_repository = _Repository(
        _facts(current=current, corrected=corrected, paid=paid)
    )
    workflow = LatePayrollObligationWorkflow(source_repository, _UnitOfWork)
    preview = workflow.preview(_intent(corrected), CorrelationId("preview"))
    request = _request(preview, key=f"mysql-disposition-{corrected}-{paid}")
    receipt = _receipt(preview)
    connection = _Connection()

    MySqlPayrollLateObligationRepository(connection).persist_payroll_disposition(
        request, preview, receipt, _command_fingerprint(request)
    )

    statements = connection.cursor_value.statements
    assert any("payroll_late_obligation_dispositions" in statement for statement in statements)
    assert all("payroll_adjustment_events" not in statement for statement in statements)
    assert all("receivable_from_staff" not in statement for statement in statements)


def test_mysql_repository_readback_is_fresh_and_source_bound():
    from infrastructure.mysql.payroll_late_obligation_repository import (
        MySqlPayrollLateObligationRepository,
    )

    class _Cursor:
        def __init__(self):
            self.calls = []
            self.result = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=()):
            self.calls.append(statement)
            if "payroll_late_obligation_dispositions" in statement:
                self.result = {"corrected_amount_ntd": 700}
            elif "FROM staff_obligations o" in statement:
                self.result = {
                    "obligation_identity": "obligation:1", "assignment_id": 8,
                    "case_no": "CASE-1", "staff_id": 17, "amount_due_ntd": 700,
                    "payroll_version": 3, "updated_at": NOW,
                    "aggregate_version": 5, "source_event_id": 7,
                    "created_at": NOW, "before_amount_ntd": 1000,
                    "after_amount_ntd": 1000, "due_date": date(2026, 8, 1),
                }
            else:
                self.result = {"paid": 1000}

        def fetchone(self):
            return self.result

    class _Connection:
        def __init__(self):
            self.cursor_value = _Cursor()

        def cursor(self):
            return self.cursor_value

    intent = _intent(700)
    readback = MySqlPayrollLateObligationRepository(_Connection()).readback_late_obligation(intent)

    assert readback.source_event_identity == intent.source_event_identity
    assert readback.current_amount == MoneyNTD(700)
    assert readback.corrected_amount == MoneyNTD(700)
    assert readback.payroll_version == 5
