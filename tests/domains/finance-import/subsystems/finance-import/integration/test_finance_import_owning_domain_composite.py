"""
File: test_finance_import_owning_domain_composite.py
Description: 驗證 Finance Import 借用 Domain context 與人工更正 dispatch。
"""

import pytest

from domains.finance_import.correction import (
    CorrectionAllocation,
    CorrectionTargetObligation,
    FinanceImportCorrectionCandidate,
    FinanceImportCorrectionFacts,
    FinanceImportCorrectionSelection,
    FinanceOwningDomain,
    build_finance_import_correction_candidate,
)
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from infrastructure.mysql.finance_import_owning_domain_composite import (
    MySqlFinanceImportOwningDomainComposite,
    _client_selection,
    _resolve_client_receipt,
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


class _VirtualAccountCursor:
    def __init__(self, responses):
        self._responses = iter(responses)
        self._current = None
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))
        self._current = next(self._responses)

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


class _VirtualAccountConnection:
    def __init__(self, responses):
        self.cursor_instance = _VirtualAccountCursor(responses)

    def cursor(self):
        return self.cursor_instance


def _pending_receipt(amount=12000):
    return CanonicalFinanceImportRow(
        "finance-import-row:97",
        0,
        MoneyNTD(amount),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("c" * 64),
    )


def test_virtual_account_resolves_one_exact_open_client_obligation() -> None:
    connection = _VirtualAccountConnection(
        (
            {
                "format_id": "sinopac",
                "cancellation_code": None,
                "bank_references": '{"銷帳編號":"99781699115150"}',
            },
            ({"case_no": "115000150"},),
            ({"obligation_identity": "client-obligation:115000150:deposit"},),
        )
    )

    resolved = _resolve_client_receipt(connection, _pending_receipt())

    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == (
        "client-obligation:115000150:deposit",
    )
    assert "exact-open-client-obligation" in resolved.evidence


def test_virtual_account_keeps_underpayment_pending() -> None:
    candidate = _pending_receipt(2400)
    connection = _VirtualAccountConnection(
        (
            {
                "format_id": "sinopac",
                "cancellation_code": None,
                "bank_references": '{"銷帳編號":"99781699115150"}',
            },
            ({"case_no": "115000150"},),
            (),
        )
    )

    assert _resolve_client_receipt(connection, candidate) == candidate


def test_normal_client_receipt_selection_never_inherits_correction_overage() -> None:
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:97",
        0,
        MoneyNTD(12000),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.CREATE,
        PreviewFingerprint("d" * 64),
        ("client-obligation:115000150:deposit",),
    )
    connection = _VirtualAccountConnection(
        (({"case_no": "115000150", "obligation_type": "deposit"},),)
    )

    selection = _client_selection(connection, candidate)

    assert selection.allow_overage_disposition is False


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


@pytest.mark.parametrize(
    ("classification_type", "post_method"),
    (
        (FinanceClassificationType.CLIENT_RECEIPT, "_post_client_receipt"),
        (FinanceClassificationType.CLIENT_REFUND, "_post_client_refund"),
        (FinanceClassificationType.CLIENT_REFUND_RETURN, "_post_client_refund_return"),
        (FinanceClassificationType.CLIENT_SUBSIDY_RETURN, "_post_client_subsidy_return"),
        (FinanceClassificationType.GOVERNMENT_SUBSIDY, "_post_government_subsidy"),
        (FinanceClassificationType.STAFF_PAYOUT, "_post_staff_payout"),
    ),
)
def test_manual_correction_dispatches_each_registered_classification_to_owner(
    monkeypatch, classification_type, post_method
) -> None:
    candidate = FinanceImportCorrectionCandidate(
        "finance-import-row:1",
        "finance-import-batch:1",
        classification_type,
        FinanceOwningDomain.GOVERNMENT_SUBSIDY
        if classification_type is FinanceClassificationType.GOVERNMENT_SUBSIDY
        else FinanceOwningDomain.STAFF_PAYABLES
        if classification_type is FinanceClassificationType.STAFF_PAYOUT
        else FinanceOwningDomain.CLIENT_FINANCE,
        MoneyNTD(100),
        (CorrectionAllocation("obligation:1", MoneyNTD(100)),),
        "reviewed",
        ("statement:1",),
        PreviewFingerprint("e" * 64),
    )
    composite = MySqlFinanceImportOwningDomainComposite(object())
    monkeypatch.setattr(composite, post_method, lambda *_args: classification_type.value)

    assert composite._post(candidate, object()) == classification_type.value


def test_non_business_review_is_not_a_manual_correction_classification() -> None:
    with pytest.raises(ValueError, match="classification_conflict"):
        FinanceImportCorrectionSelection(
            "finance-import-row:1",
            FinanceClassificationType.NON_BUSINESS_REVIEW,
            ("obligation:1",),
            "reviewed",
            ("statement:1",),
        )
