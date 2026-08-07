import pytest

from subsystems.finance_import import reconciliation_dispatch


def test_identity_ids_are_positive_unique_and_preserve_order() -> None:
    assert reconciliation_dispatch._identity_ids("[3,2,3]") == [3, 2]
    assert reconciliation_dispatch._identity_ids("[0]") is None


def test_non_business_row_stays_pending_without_domain_call(monkeypatch) -> None:
    monkeypatch.setattr(
        reconciliation_dispatch,
        "_dispatch_row",
        lambda *_args: {
            "classification_type": "non_business_review",
            "classification_reason": "needs_human_review",
        },
    )

    result = reconciliation_dispatch.dispatch_finance_import_row(_Cursor(), 7, 4)

    assert result == {
        "classification_type": "non_business_review",
        "result": "pending",
        "reason": "needs_human_review",
        "formal_references": {},
        "finance_alert_action": None,
    }


def test_staff_row_requires_exactly_one_transfer_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        reconciliation_dispatch,
        "_dispatch_row",
        lambda *_args: {"classification_type": "staff_salary"},
    )
    monkeypatch.setattr(reconciliation_dispatch, "_staff_transfer_candidates", lambda *_args: [])

    result = reconciliation_dispatch.dispatch_finance_import_row(_Cursor(), 7, 4)

    assert result["result"] == "pending"
    assert result["reason"] == "staff_transfer_plan_not_unique"


def test_legacy_subsidy_return_dispatch_is_fail_closed() -> None:
    result = reconciliation_dispatch.dispatch_finance_import_row(
        _SubsidyReturnCursor(),
        7,
        4,
    )

    assert result["result"] == "pending"
    assert result["reason"] == "legacy_client_subsidy_return_dispatch_retired"


def test_dispatch_rejects_nonpositive_identity() -> None:
    with pytest.raises(ValueError, match="finance_import_row_id"):
        reconciliation_dispatch.dispatch_finance_import_row(_Cursor(), 0, 4)


class _Cursor:
    def execute(self, *_args):
        return None


class _SubsidyReturnCursor:
    def execute(self, *_args):
        return None

    def fetchone(self):
        return {
            "id": 7,
            "classification_type": "client_subsidy_return",
            "matched_identity_ids": "[1]",
            "resolved_counterparty_account": "A",
            "classification_reason": "legacy",
            "debit": 100,
        }
