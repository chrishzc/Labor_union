from domains.anomalies.current_issue import RecheckScope, build_owner_lock_key
from infrastructure.mysql.government_subsidy_current_issue_adapter import (
    MySqlGovernmentSubsidyCurrentIssueAdapter,
)


class _Cursor:
    def __init__(self, responses):
        self.responses = responses
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current


class _Connection:
    def __init__(self, responses):
        self.responses = list(responses)

    def cursor(self):
        return _Cursor(self.responses)


def _scope(code, subject, root):
    return RecheckScope(
        "government_subsidy", "government_subsidy_current_fact", code,
        (subject,),
        (build_owner_lock_key("government_subsidy", "government_subsidy_current_fact", root),),
    )


def test_receipt_terminal_requires_full_allocation_conservation() -> None:
    row = {
        "finance_import_row_id": 11,
        "classification_type": "government_subsidy", "owner_version": 3,
        "eligible_batch_count": 1, "claim_batch_id": 5,
        "transaction_status": "succeeded", "transaction_amount_ntd": 5600,
        "bank_amount_ntd": 5600, "allocation_total_ntd": 5600,
        "allocation_count": 1,
    }
    snapshot = MySqlGovernmentSubsidyCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("GOVSUB-001", "bank-1", "bank:bank-1")
    )
    assert snapshot.facts[0].predicate_active is False


def test_manual_allocation_over_limit_stays_active() -> None:
    row = {
        "finance_import_row_id": 11,
        "classification_type": "government_subsidy", "owner_version": 4,
        "claim_batch_id": 5, "transaction_status": "succeeded",
        "transaction_amount_ntd": 5600, "bank_amount_ntd": 5600,
        "allocation_total_ntd": 5600, "allocation_count": 2,
        "invalid_item_count": 1,
    }
    snapshot = MySqlGovernmentSubsidyCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("GOVSUB-002", "bank-1:5", "bank:bank-1")
    )
    assert snapshot.facts[0].item_outstanding_valid is False
    assert snapshot.facts[0].predicate_active is True


def test_reversal_terminal_requires_exact_source_and_complete_allocations() -> None:
    row = {
        "finance_import_row_id": 12,
        "classification_type": "government_subsidy", "owner_version": 8,
        "target_count": 1, "source_transaction_type": "receipt",
        "source_transaction_status": "succeeded",
        "reversal_transaction_status": "succeeded",
        "reversal_of_transaction_id": 91, "source_receipt_id": 91,
        "reversal_allocation_total_ntd": 1200, "bank_amount_ntd": 1200,
        "invalid_reversal_count": 0,
    }
    snapshot = MySqlGovernmentSubsidyCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("GOVSUB-004", "bank-out-1:91", "receipt:91")
    )
    assert snapshot.facts[0].predicate_active is False
