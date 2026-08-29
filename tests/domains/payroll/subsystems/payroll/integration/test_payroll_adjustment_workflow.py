from datetime import date

import pytest

from domains.payroll.adjustment import (
    EffectivePayrollAssignment,
    PayrollAdjustmentAllocationIntent,
    PayrollAdjustmentFacts,
    PayrollAdjustmentIntent,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.adjustment_workflow import (
    PayrollAdjustmentApplyRequest,
    PayrollAdjustmentError,
    PayrollAdjustmentWorkflow,
    StoredPayrollAdjustmentReceipt,
)


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []
        self.load_modes = []

    def load(self, case_no, *, for_update):
        assert case_no == self.facts.case_no
        self.load_modes.append(for_update)
        return self.facts

    def find_receipt(self, key):
        return self.receipt

    def persist(self, request, preview, command_fingerprint, receipt):
        self.persisted.append((request, preview, command_fingerprint, receipt))


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def _facts(version=4):
    return PayrollAdjustmentFacts(
        "CASE-1",
        version,
        date(2026, 8, 31),
        (EffectivePayrollAssignment(8, 17),),
    )


def _intent(amount=300):
    return PayrollAdjustmentIntent(
        "CASE-1",
        "terms-change:1",
        (PayrollAdjustmentAllocationIntent(8, MoneyNTD(amount)),),
    )


def _request(preview, *, key="adjustment-1", version=4):
    return PayrollAdjustmentApplyRequest(
        _intent(),
        ExpectedVersion(version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("admin"),
        "Correct a signed service amount.",
        CorrelationId("payroll-adjustment-test"),
    )


def test_preview_and_apply_persist_one_versioned_payroll_adjustment():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = PayrollAdjustmentWorkflow(repository, lambda: unit_of_work)

    preview = workflow.preview(_intent(), CorrelationId("preview-test"))
    receipt = workflow.apply(_request(preview))

    assert repository.load_modes == [False, True]
    assert unit_of_work.committed is True
    assert receipt.payroll_version == 5
    assert receipt.amount_ntd == 300
    assert receipt.allocation_count == 1
    assert repository.persisted[0][3] == receipt


def test_apply_replays_exact_idempotency_command_without_transaction():
    repository = _Repository(_facts())
    workflow = PayrollAdjustmentWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent(), CorrelationId("preview-test"))
    request = _request(preview)
    expected_receipt = workflow.apply(request)
    repository.receipt = StoredPayrollAdjustmentReceipt(
        repository.persisted[0][2],
        expected_receipt,
    )
    repository.persisted.clear()
    repository.load_modes.clear()

    assert workflow.apply(request) == expected_receipt
    assert repository.load_modes == []
    assert repository.persisted == []


def test_apply_rejects_stale_payroll_version_before_persistence():
    repository = _Repository(_facts(version=5))
    workflow = PayrollAdjustmentWorkflow(repository, _UnitOfWork)
    preview = PayrollAdjustmentWorkflow(
        _Repository(_facts(version=4)),
        _UnitOfWork,
    ).preview(_intent(), CorrelationId("preview-test"))

    with pytest.raises(PayrollAdjustmentError) as raised:
        workflow.apply(_request(preview, version=4))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "payroll_candidate_stale"
    assert repository.persisted == []


def test_apply_rejects_reused_idempotency_key_for_another_command():
    repository = _Repository(_facts())
    workflow = PayrollAdjustmentWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent(), CorrelationId("preview-test"))
    request = _request(preview)
    prior_receipt = workflow.apply(request)
    repository.receipt = StoredPayrollAdjustmentReceipt(
        repository.persisted[0][2],
        prior_receipt,
    )
    different_request = PayrollAdjustmentApplyRequest(
        _intent(-300),
        request.expected_payroll_version,
        request.preview_fingerprint,
        request.idempotency_key,
        request.actor,
        request.reason,
        request.correlation_id,
    )

    with pytest.raises(PayrollAdjustmentError) as raised:
        workflow.apply(different_request)

    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH
    assert raised.value.error.code == "idempotency_conflict"
