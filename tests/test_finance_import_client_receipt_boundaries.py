import pytest

from subsystems.finance_import import reconciliation_dispatch as importer


class Cursor:
    def execute(self, sql, params=None):
        pass


@pytest.mark.parametrize(
    "reason",
    [
        "virtual_account_invalid",
        "client_payment_not_found",
        "client_payment_not_unique",
        "receipt_exceeds_remaining",
        "snapshot_terms_incomplete",
    ],
)
def test_client_receipt_boundary_result_is_preserved_as_pending(monkeypatch, reason):
    """FinanceImport must not replace a receipt service boundary decision with a guess."""
    expected = {"result": "pending", "reason": reason}
    calls = []

    def reconcile(cursor, row_id):
        calls.append(row_id)
        return expected

    monkeypatch.setattr(importer, "reconcile_client_receipt", reconcile)
    monkeypatch.setattr(
        importer,
        "_dispatch_row",
        lambda cursor, row_id: {
            "id": row_id,
            "classification_type": "client_receipt",
        },
    )
    monkeypatch.setattr(importer, "maybe_alert_pending", lambda *args, **kwargs: None)

    result = importer.dispatch_finance_import_row(Cursor(), 801, 51)

    assert calls == [801]
    assert result == {
        "classification_type": "client_receipt",
        "result": "pending",
        "reason": reason,
        "formal_references": {},
        "finance_alert_action": None,
    }


def test_non_business_incoming_row_is_pending_without_client_receipt_side_effect(monkeypatch):
    called = []
    monkeypatch.setattr(
        importer,
        "reconcile_client_receipt",
        lambda cursor, row_id: called.append(row_id),
    )
    monkeypatch.setattr(
        importer,
        "_dispatch_row",
        lambda cursor, row_id: {
            "id": row_id,
            "classification_type": "non_business_review",
            "classification_reason": "sinopac_invalid_or_missing_virtual_account",
        },
    )

    result = importer.dispatch_finance_import_row(Cursor(), 802, 51)

    assert result == {
        "classification_type": "non_business_review",
        "result": "pending",
        "reason": "sinopac_invalid_or_missing_virtual_account",
        "formal_references": {},
        "finance_alert_action": None,
    }
    assert called == []
