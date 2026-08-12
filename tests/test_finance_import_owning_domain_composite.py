"""Bounded regression tests for Finance Import's borrowed-domain context."""

import pytest

from domains.finance_import.correction import (
    CorrectionTargetObligation,
    FinanceImportCorrectionFacts,
    FinanceImportCorrectionSelection,
    FinanceOwningDomain,
    build_finance_import_correction_candidate,
)
from domains.finance_import.planning import FinanceClassificationType
from infrastructure.mysql.finance_import_owning_domain_composite import (
    _request_reason,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionApplyRequest,
)
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessApplyRequest,
)


def test_correction_posting_context_uses_the_validated_selection_reason() -> None:
    selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "bank statement was reviewed",
        ("bank-statement:line-1",),
    )
    request = FinanceImportCorrectionApplyRequest(
        selection,
        ExpectedVersion(0),
        ExpectedVersion(0),
        ExpectedVersion(0),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("correction-context-reason"),
        ActorContext("test-operator"),
        CorrelationId("correction-context-reason"),
    )

    assert _request_reason(request) == "bank statement was reviewed"


def test_historical_reprocess_posting_context_keeps_its_request_reason() -> None:
    request = HistoricalReprocessApplyRequest(
        "finance-import-batch:1",
        ExpectedVersion(0),
        PreviewFingerprint("b" * 64),
        IdempotencyKey("historical-context-reason"),
        ActorContext("test-operator"),
        "historical owner selection was reviewed",
        CorrelationId("historical-context-reason"),
    )

    assert _request_reason(request) == "historical owner selection was reviewed"


def test_partial_refund_recovery_requires_an_explicit_operator_choice() -> None:
    facts = FinanceImportCorrectionFacts(
        "finance-import-batch:1",
        0,
        0,
        0,
        MoneyNTD(300),
        True,
        (
            CorrectionTargetObligation(
                "refund:C-1",
                FinanceOwningDomain.CLIENT_FINANCE,
                MoneyNTD(500),
            ),
        ),
    )
    normal_selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "bank statement was reviewed",
        ("bank-statement:line-1",),
    )

    with pytest.raises(ValueError, match="allocation_not_exact"):
        build_finance_import_correction_candidate(normal_selection, facts)

    recovery_selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "operator confirmed an actual underpayment",
        ("bank-statement:line-1",),
        allow_partial_refund_recovery=True,
    )
    candidate = build_finance_import_correction_candidate(recovery_selection, facts)

    assert candidate.allow_partial_refund_recovery is True
    assert candidate.allocations[0].amount == MoneyNTD(300)
