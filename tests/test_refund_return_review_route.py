from api.routes.finance_import import (
    apply_refund_return_review,
    preview_refund_return_review,
)
from api.schemas.finance_import import (
    RefundReturnReviewApplyBody,
    RefundReturnReviewPreviewBody,
)
from domains.client_finance.refund_return_review import (
    RefundReturnReviewFacts,
    build_refund_return_review_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.finance_import.refund_return_review_workflow import (
    RefundReturnReviewPreview,
    RefundReturnReviewReceipt,
)


def test_preview_exposes_server_derived_refund_return_review_fingerprint():
    application = _Application()

    response = preview_refund_return_review(
        RefundReturnReviewPreviewBody(
            finance_import_row_id=71,
            original_refund_ledger_entry_id=41,
            case_no="C-1",
            reason="bank return receipt verified",
            evidence=["bank-return-document:7"],
        ),
        principal=_principal(),
        application=application,
    )

    assert response.data["row_identity"] == "finance-import-row:71"
    assert response.data["original_refund_ledger_entry_identity"] == "client-ledger-entry:41"
    assert response.data["preview_fingerprint"] == "b" * 64


def test_apply_uses_authenticated_actor_and_idempotency_key():
    application = _Application()

    response = apply_refund_return_review(
        RefundReturnReviewApplyBody(
            finance_import_row_id=71,
            original_refund_ledger_entry_id=41,
            case_no="C-1",
            reason="bank return receipt verified",
            evidence=["bank-return-document:7"],
            expected_batch_version=3,
            preview_fingerprint="b" * 64,
        ),
        idempotency_key="refund-return-review-key",
        correlation_id="refund-return-review-apply",
        principal=_principal(),
        application=application,
    )

    assert response.data["review_event_identity"] == "client-refund-return-review:12"
    assert application.request.idempotency_key.value == "refund-return-review-key"
    assert application.request.actor.actor_id == "admin"


def _principal():
    return AdminPrincipal(1, "admin", "Admin", "system_admin")


class _Application:
    request = None

    def preview(self, selection, _correlation_id):
        candidate = build_refund_return_review_candidate(
            selection,
            RefundReturnReviewFacts(
                "finance-import-batch:4",
                3,
                MoneyNTD(300),
                True,
                MoneyNTD(300),
                True,
                "C-1",
            ),
        )
        return RefundReturnReviewPreview(candidate, 3, PreviewFingerprint("b" * 64))

    def apply(self, request):
        self.request = request
        return RefundReturnReviewReceipt(
            "client-refund-return-review:12",
            request.selection.row_identity,
            request.selection.original_refund_ledger_entry_identity,
            request.preview_fingerprint,
        )
