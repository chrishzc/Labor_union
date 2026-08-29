"""
File: test_client_over_refund_recovery_contract.py
Description: 驗證客戶追償 evidence、replay conflict 與 strict owner Query。
"""

from pydantic import ValidationError
import pytest

from api.schemas.client_refund_reversal import (
    ClientOverRefundRecoveryAdjustmentPreviewBody,
    ClientOverRefundRecoveryMatchingPreviewBody,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.client_over_refund_recovery_query import (
    ClientOverRefundRecoveryQueryFacts,
    ClientOverRefundRecoveryQuerySelection,
    ClientOverRefundRecoveryQueryWorkflow,
)
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingApplyRequest,
    ClientOverRefundRecoveryMatchingFacts,
    ClientOverRefundRecoveryMatchingSelection,
    ClientOverRefundRecoveryMatchingWorkflow,
    ClientOverRefundRecoveryMatchingError,
)


def test_recovery_preview_bodies_require_independent_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        ClientOverRefundRecoveryMatchingPreviewBody.model_validate(
            {"recovery_identity": "recovery:1", "finance_import_row_id": 7}
        )
    with pytest.raises(ValidationError):
        ClientOverRefundRecoveryAdjustmentPreviewBody.model_validate(
            {"recovery_identity": "recovery:1", "adjustment_amount_ntd": 10}
        )


def test_same_key_with_changed_evidence_is_an_idempotency_conflict() -> None:
    repository = _ReplayRepository()
    workflow = ClientOverRefundRecoveryMatchingWorkflow(repository, _UnitOfWork)
    selection = ClientOverRefundRecoveryMatchingSelection(
        "115000001", "recovery:1", "7", "evidence:one"
    )
    preview = workflow.preview(selection, CorrelationId("preview"))
    request = ClientOverRefundRecoveryMatchingApplyRequest(
        selection, ExpectedVersion(1), ExpectedVersion(4), preview.fingerprint,
        IdempotencyKey("same-key"), ActorContext("admin:1"), "reviewed",
        CorrelationId("apply"), "evidence:one"
    )
    workflow.apply(request)
    changed = ClientOverRefundRecoveryMatchingApplyRequest(
        selection, ExpectedVersion(1), ExpectedVersion(4), preview.fingerprint,
        IdempotencyKey("same-key"), ActorContext("admin:1"), "reviewed",
        CorrelationId("apply-retry"), "evidence:two"
    )
    with pytest.raises(ClientOverRefundRecoveryMatchingError) as raised:
        workflow.apply(changed)
    assert raised.value.error.code == "idempotency_conflict"


def test_owner_query_is_strict_and_zero_write() -> None:
    repository = _QueryRepository()
    workflow = ClientOverRefundRecoveryQueryWorkflow(repository)
    result = workflow.query(
        ClientOverRefundRecoveryQuerySelection("115000001", "recovery:1"),
        CorrelationId("query"),
    )
    assert result.source_row_reference == "finance-import-row:9"
    assert [item.incoming_row_reference for item in result.current_matchings] == [
        "finance-import-row:11", "finance-import-row:12"
    ]
    assert repository.writes == []

    from subsystems.client_finance.client_over_refund_recovery_query import (
        ClientOverRefundRecoveryQueryError,
    )
    with pytest.raises(ClientOverRefundRecoveryQueryError) as raised:
        workflow.query(
            ClientOverRefundRecoveryQuerySelection("115000002", "recovery:1"),
            CorrelationId("owner-mismatch"),
        )
    assert raised.value.error.code == "client_over_refund_recovery_owner_mismatch"
    assert repository.writes == []


@pytest.mark.parametrize(
    ("status", "remaining"),
    (("open", 0), ("partially_recovered", 0), ("recovered", 1), ("adjusted", 1)),
)
def test_owner_query_rejects_status_remaining_contradiction(status, remaining) -> None:
    with pytest.raises(ValueError, match="client_over_refund_recovery_query_invalid"):
        ClientOverRefundRecoveryQueryFacts(
            "115000001", "recovery:1", remaining, status, 3, 4,
            "finance-import-row:9", (),
        )


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _ReplayRepository:
    def __init__(self):
        self.receipt = None

    def load_matching(self, selection, *, for_update):
        return ClientOverRefundRecoveryMatchingFacts(1, 4, True)

    def find_matching_receipt(self, key):
        return self.receipt

    def persist_matching(self, request, preview, receipt, command_fingerprint):
        from subsystems.client_finance.over_refund_recovery_matching_workflow import (
            StoredClientOverRefundRecoveryMatchingReceipt,
        )
        self.receipt = StoredClientOverRefundRecoveryMatchingReceipt(command_fingerprint, receipt)


class _QueryRepository:
    def __init__(self):
        self.writes = []

    def query_recovery(self, selection):
        return ClientOverRefundRecoveryQueryFacts(
            selection.case_no if selection.case_no == "115000001" else "115000001",
            "recovery:1", 250, "open", 3, 4, "finance-import-row:9",
            (
                # Query facts are already redacted; raw bank payload never crosses this boundary.
                _matching("matching:1", 1, "finance-import-row:11"),
                _matching("matching:2", 1, "finance-import-row:12"),
            ),
        )


def _matching(identity, version, reference):
    from subsystems.client_finance.client_over_refund_recovery_query import (
        ClientOverRefundRecoveryMatchingQueryFact,
    )
    return ClientOverRefundRecoveryMatchingQueryFact(identity, version, reference)
