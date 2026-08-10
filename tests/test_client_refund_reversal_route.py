"""Route-level regressions for distinct Client Finance refund operations."""

from types import SimpleNamespace

from api.routes.client_refund_reversal import apply_subsidy_return
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
