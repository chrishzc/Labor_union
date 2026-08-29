from datetime import date

import pytest

from domains.payroll.calculation import (
    OfficialAssignmentServiceFacts,
    PayrollTerms,
    PayrollPolicyKind,
    rate_snapshot,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.rebuild_workflow import (
    ExistingStaffObligation,
    PayrollRebuildError,
    PayrollRebuildFacts,
    PayrollRebuildRequest,
    PayrollRebuildWorkflow,
    StaffObligationActionKind,
    StoredPayrollReceipt,
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

    def persist_rebuild(self, persistence):
        self.persisted.append(persistence)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def commit(self):
        self.committed = True


def _facts(existing=(), version=4, due_date=date(2026, 9, 15)):
    identity = "assignment:8"
    return PayrollRebuildFacts(
        "CASE-1",
        version,
        (OfficialAssignmentServiceFacts(identity, 17, (date(2026, 8, 1),)),),
        (rate_snapshot(identity, "policy-1", PayrollPolicyKind.CITIZEN),),
        PayrollTerms(1, 8, MoneyNTD(1000)),
        (),
        existing,
        due_date,
    )


def _request(preview, *, version=4, key="payroll-rebuild-1"):
    return PayrollRebuildRequest(
        "CASE-1",
        ExpectedVersion(version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("admin"),
        "Rebuild root-fact payroll obligations.",
        CorrelationId("payroll-rebuild-test"),
    )


def test_preview_classifies_create_replace_frozen_and_removed_actions():
    create = PayrollRebuildWorkflow(_Repository(_facts()), _UnitOfWork).preview("CASE-1")
    total = create.payroll.total_payable
    replace = ExistingStaffObligation("assignment:8", "old-8", MoneyNTD(1), False, date(2026, 9, 15))
    frozen = ExistingStaffObligation("assignment:8", "old-8", MoneyNTD(1), True, date(2026, 9, 15))
    removed = ExistingStaffObligation("assignment:9", "old-9", MoneyNTD(20), False, date(2026, 9, 15))

    replace_preview = PayrollRebuildWorkflow(_Repository(_facts((replace,))), _UnitOfWork).preview("CASE-1")
    frozen_preview = PayrollRebuildWorkflow(_Repository(_facts((frozen,))), _UnitOfWork).preview("CASE-1")
    removed_preview = PayrollRebuildWorkflow(_Repository(_facts((removed,))), _UnitOfWork).preview("CASE-1")

    assert create.actions[0].action is StaffObligationActionKind.CREATE
    assert create.actions[0].after_amount == total
    assert replace_preview.actions[0].action is StaffObligationActionKind.REPLACE_UNPAID
    assert frozen_preview.actions[0].action is StaffObligationActionKind.APPEND_FROZEN_DELTA
    assert removed_preview.actions[0].action is StaffObligationActionKind.CREATE
    assert removed_preview.actions[1].action is StaffObligationActionKind.REPLACE_UNPAID
    assert removed_preview.actions[1].after_amount == MoneyNTD(0)


def test_preview_rebuilds_unpaid_obligation_when_orders_first_forms_due_date():
    existing = ExistingStaffObligation(
        "assignment:8",
        "old-8",
        MoneyNTD(3400),
        False,
        None,
    )

    preview = PayrollRebuildWorkflow(
        _Repository(_facts((existing,))),
        _UnitOfWork,
    ).preview("CASE-1")

    assert preview.actions[0].action is StaffObligationActionKind.REPLACE_UNPAID
    assert preview.actions[0].before_amount == preview.actions[0].after_amount
    assert preview.actions[0].due_date == date(2026, 9, 15)


def test_preview_does_not_rewrite_existing_non_null_due_date():
    existing = ExistingStaffObligation(
        "assignment:8",
        "old-8",
        MoneyNTD(3400),
        False,
        date(2026, 9, 15),
    )

    preview = PayrollRebuildWorkflow(
        _Repository(_facts((existing,), due_date=date(2026, 10, 15))),
        _UnitOfWork,
    ).preview("CASE-1")

    assert preview.actions[0].action is StaffObligationActionKind.UNCHANGED
    assert preview.actions[0].due_date == date(2026, 9, 15)


def test_apply_persists_one_fresh_preview_and_replays_matching_idempotency_key():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = PayrollRebuildWorkflow(repository, lambda: unit_of_work)
    preview = workflow.preview("CASE-1")
    request = _request(preview)

    receipt = workflow.apply(request)
    repository.receipt = StoredPayrollReceipt(repository.persisted[0].command_fingerprint, receipt)
    replay = workflow.apply(request)

    assert repository.load_modes == [False, True]
    assert len(repository.persisted) == 1
    assert receipt.payroll_version == 5
    assert receipt.action_count == 1
    assert replay == receipt
    assert unit_of_work.committed is True


def test_apply_rejects_stale_preview_version_with_typed_conflict():
    repository = _Repository(_facts(version=5))
    workflow = PayrollRebuildWorkflow(repository, _UnitOfWork)
    preview = PayrollRebuildWorkflow(_Repository(_facts()), _UnitOfWork).preview("CASE-1")

    with pytest.raises(PayrollRebuildError) as raised:
        workflow.apply(_request(preview, version=4))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "payroll_candidate_stale"
