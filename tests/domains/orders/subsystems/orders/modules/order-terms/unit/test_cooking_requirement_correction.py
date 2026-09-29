"""Uniquely sourced cooking correction preserves the Orders mutation boundary."""

from dataclasses import replace

import pytest

from domains.orders.terms import OrderCookingRequirementFacts
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.orders.terms_workflow import (
    OrderCookingRequirementCorrectionRequest,
    OrderTermsWorkflow,
    TermsWorkflowError,
)


class _Repository:
    def __init__(self, facts, update_succeeds=True):
        self.facts = facts
        self.updates = []
        self.update_succeeds = update_succeeds

    def load_cooking_requirement(self, case_no, *, for_update):
        assert for_update is True
        assert case_no == self.facts.case_no
        return self.facts

    def update_cooking_requirement(self, case_no, requires_cooking, version):
        self.updates.append((case_no, requires_cooking, version))
        if self.update_succeeds:
            self.facts = replace(self.facts, version=version + 1, requires_cooking=requires_cooking)
        return self.update_succeeds


def _forbidden_uow():
    raise AssertionError("the caller owns the transaction")


def _request(value=True):
    return OrderCookingRequirementCorrectionRequest(
        "COOKING-TEST", value, ExpectedVersion(4), CorrelationId("test-cooking"),
    )


@pytest.mark.parametrize("value", [True, False])
def test_unknown_cooking_correction_is_replay_safe_in_caller_uow(value):
    repository = _Repository(OrderCookingRequirementFacts("COOKING-TEST", 4, None, False))
    workflow = OrderTermsWorkflow(repository, _forbidden_uow, None)

    assert workflow.correct_cooking_requirement_in_current_uow(_request(value)) == 5
    assert workflow.correct_cooking_requirement_in_current_uow(_request(value)) == 5
    assert repository.updates == [("COOKING-TEST", value, 4)]


@pytest.mark.parametrize("version,current,locked,code,category", [
    (5, None, False, "order_version_conflict", ErrorCategory.CONFLICT),
    (4, None, True, "service_data_locked", ErrorCategory.DOMAIN_BLOCKED),
    (4, False, False, "cooking_requirement_already_known", ErrorCategory.DOMAIN_BLOCKED),
])
def test_fresh_conflict_or_lock_prevents_cooking_write(version, current, locked, code, category):
    repository = _Repository(OrderCookingRequirementFacts("COOKING-TEST", version, current, locked))
    workflow = OrderTermsWorkflow(repository, _forbidden_uow, None)

    with pytest.raises(TermsWorkflowError) as captured:
        workflow.correct_cooking_requirement_in_current_uow(_request())

    assert captured.value.error.code == code
    assert captured.value.error.category is category
    assert repository.updates == []


def test_compare_and_set_failure_is_a_typed_conflict():
    repository = _Repository(OrderCookingRequirementFacts("COOKING-TEST", 4, None, False), False)
    workflow = OrderTermsWorkflow(repository, _forbidden_uow, None)
    with pytest.raises(TermsWorkflowError) as captured:
        workflow.correct_cooking_requirement_in_current_uow(_request())
    assert captured.value.error.code == "order_version_conflict"
    assert captured.value.error.category is ErrorCategory.CONFLICT
