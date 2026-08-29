from datetime import date

import pytest

from domains.government_subsidy.payer_master import (
    PAYER_IDENTITY,
    PAYER_NAME,
    GovernmentPayerMaster,
    GovernmentPayerMasterError,
    GovernmentRefundAccount,
    GovernmentRefundAccountVersion,
)
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.government_subsidy.payer_master_workflow import (
    GovernmentPayerMasterWorkflow,
    GovernmentPayerMasterWorkflowError,
    GovernmentRefundAccountApplyRequest,
)


class UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class Repository:
    def __init__(self, active=None):
        self.active = active
        self.appended = []

    def load_master(self, *, lock):
        return GovernmentPayerMaster(PAYER_IDENTITY, PAYER_NAME, self.active)

    def append_account_version(self, account, actor_id):
        if self.appended and self.appended[0][0] == account:
            return False
        self.appended.append((account, actor_id))
        self.active = GovernmentRefundAccountVersion(account, None)
        return True

    def account_display(self, account_number):
        return "*" * (len(account_number) - 4) + account_number[-4:]


def _account(day=1):
    return GovernmentRefundAccount("004", "012345678901", "新竹市政府", date(2026, 8, day), "政府公文", "letter-1")


def _request(account, fingerprint):
    return GovernmentRefundAccountApplyRequest(account, fingerprint, ActorContext("admin:1"), CorrelationId("test"))


def test_empty_singleton_can_preview_and_append_first_account_version():
    repository = Repository()
    workflow = GovernmentPayerMasterWorkflow(repository, UnitOfWork)

    preview = workflow.preview(_account())
    receipt = workflow.apply(_request(_account(), preview.fingerprint))

    assert receipt.account_display == "********8901"
    assert receipt.replayed is False
    assert len(repository.appended) == 1


def test_new_version_must_be_later_than_active_version():
    repository = Repository(GovernmentRefundAccountVersion(_account(2), None))
    workflow = GovernmentPayerMasterWorkflow(repository, UnitOfWork)

    with pytest.raises(GovernmentPayerMasterError, match="government_payer_account_effective_date_invalid"):
        workflow.preview(_account(2))


def test_apply_refuses_stale_preview_before_writing():
    repository = Repository()
    workflow = GovernmentPayerMasterWorkflow(repository, UnitOfWork)
    preview = workflow.preview(_account())
    repository.active = GovernmentRefundAccountVersion(_account(2), None)

    with pytest.raises(GovernmentPayerMasterWorkflowError, match="government_payer_account_preview_stale"):
        workflow.apply(_request(_account(3), preview.fingerprint))
    assert repository.appended == []


def test_api_account_view_never_contains_raw_account_field():
    from api.schemas.government_subsidy import GovernmentPayerAccountView

    assert "account_number" not in GovernmentPayerAccountView.model_fields
