"""Zero grant is a valid approval, never a zero-value bank allocation."""
from types import SimpleNamespace
import pytest

from api.routes.government_subsidy import _approval_intent
from api.schemas.government_subsidy import GovernmentSubsidyApprovalItemView
from api.dependencies.durable_job_handlers import _government_subsidy_request
from domains.government_subsidy.ledger import AllocationIntent, ClaimItemApproval, validate_approval_amounts
from shared_kernel.money import MoneyNTD


def test_zero_approval_survives_http_and_durable_worker_without_weakening_bank_allocations():
    approval = GovernmentSubsidyApprovalItemView(item_id=1, approved_amount_ntd=0)
    intent = _approval_intent(1, [approval])
    request = _government_subsidy_request({
        'action': 'claim_approval', 'intent': {'batch_id': 1, 'item_approvals': [approval.model_dump()]},
        'expected_batch_version': 2, 'preview_fingerprint': 'a' * 64,
        'idempotency_key': 'zero-approval', 'actor': 'test', 'reason': '', 'correlation_id': 'zero-approval',
    })
    assert request.intent == intent
    assert validate_approval_amounts((SimpleNamespace(item_id=1, requested_amount_ntd=MoneyNTD(100)),), intent.item_approvals) == MoneyNTD(0)
    with pytest.raises(ValueError, match='must be positive'):
        AllocationIntent(1, MoneyNTD(0))
    with pytest.raises(ValueError, match='must be nonnegative'):
        ClaimItemApproval(1, MoneyNTD(-1))
