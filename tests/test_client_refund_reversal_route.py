"""Route-level regressions for distinct Client Finance refund operations."""

from types import SimpleNamespace

from api.routes.client_refund_reversal import (
    apply_subsidy_return,
    query_settlement_remediation,
)
from api.schemas.client_refund_reversal import ClientRefundApplyBody


def test_subsidy_return_apply_uses_the_dedicated_purpose_and_executes_workflow():
    requests: list[object] = []

    class Application:
        def apply(self, request):
            requests.append(request)
            return {"correction_type": "refund", "ledger_entry_count": 1}

    response = apply_subsidy_return(
        ClientRefundApplyBody(
            finance_import_row_ids=[17],
            obligation_identities=["subsidy:CASE-1"],
            expected_account_version=3,
            preview_fingerprint="a" * 64,
            reason="政府補助退還已由銀行出款",
        ),
        "CASE-1",
        "subsidy-return-apply-1",
        "refund-route-test",
        SimpleNamespace(username="test-admin"),
        Application(),
    )

    assert response.data == {"correction_type": "refund", "ledger_entry_count": 1}
    assert len(requests) == 1
    assert requests[0].selection.refund_purpose.value == "subsidy_return"
    assert requests[0].selection.correction_type.value == "refund"


def test_settlement_remediation_query_returns_only_current_overdue_owner_facts():
    class RefundApplication:
        def query(self, case_no):
            assert case_no == "CASE-2"
            return {
                "account_version": 5,
                "refund_obligations": [
                    {
                        "obligation_identity": "refund:old",
                        "obligation_type": "refund",
                        "amount_due_ntd": 1200,
                        "due_date": __import__("datetime").date(2026, 1, 1),
                    },
                    {
                        "obligation_identity": "refund:future",
                        "obligation_type": "refund",
                        "amount_due_ntd": 800,
                        "due_date": __import__("datetime").date(2099, 1, 1),
                    },
                ],
                "subsidy_return_obligations": [],
                "refund_bank_facts": [],
                "subsidy_return_bank_facts": [],
            }

    class ReceiptApplication:
        def query(self, case_no):
            assert case_no == "CASE-2"
            return {
                "account_version": 5,
                "obligations": [
                    {
                        "obligation_identity": "receipt:old",
                        "payment_stage": "first",
                        "amount_due_ntd": 1500,
                        "due_date": __import__("datetime").date(2026, 1, 1),
                    }
                ],
                "bank_facts": [],
            }

    response = query_settlement_remediation(
        "CASE-2",
        SimpleNamespace(username="test-admin"),
        RefundApplication(),
        ReceiptApplication(),
    )

    assert response.data["account_version"] == 5
    assert [item["obligation_identity"] for item in response.data["refund_obligations"]] == [
        "refund:old"
    ]
    assert [item["obligation_identity"] for item in response.data["receivable_obligations"]] == [
        "receipt:old"
    ]
