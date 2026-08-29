from domains.finance_import.correction import (
    CorrectionTargetObligation,
    FinanceImportCorrectionFacts,
    FinanceImportCorrectionSelection,
    FinanceOwningDomain,
    build_finance_import_correction_candidate,
)
from domains.finance_import.planning import FinanceClassificationType
from shared_kernel.money import MoneyNTD


def test_client_receipt_overage_uses_only_the_real_receivable_amount() -> None:
    candidate = build_finance_import_correction_candidate(
        _selection(FinanceClassificationType.CLIENT_RECEIPT, client_receipt_overage=True),
        _facts(3000, 2500),
    )

    assert [item.amount for item in candidate.allocations] == [MoneyNTD(2500)]
    assert candidate.allow_client_receipt_overage is True


def test_client_refund_overage_uses_only_the_real_refund_amount() -> None:
    candidate = build_finance_import_correction_candidate(
        _selection(FinanceClassificationType.CLIENT_REFUND, refund_overage=True),
        _facts(750, 500),
    )

    assert [item.amount for item in candidate.allocations] == [MoneyNTD(500)]
    assert candidate.allow_refund_overage_recovery is True


def _selection(classification, *, client_receipt_overage=False, refund_overage=False):
    return FinanceImportCorrectionSelection(
        "row-1", classification, ("obligation-1",), "confirmed", ("statement",),
        allow_refund_overage_recovery=refund_overage,
        allow_client_receipt_overage=client_receipt_overage,
    )


def _facts(bank_amount: int, obligation_amount: int):
    return FinanceImportCorrectionFacts(
        "batch-1", 1, 1, 1, MoneyNTD(bank_amount), True,
        (CorrectionTargetObligation("obligation-1", FinanceOwningDomain.CLIENT_FINANCE, MoneyNTD(obligation_amount)),),
    )
