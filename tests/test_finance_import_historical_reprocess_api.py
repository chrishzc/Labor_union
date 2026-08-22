"""
File: test_finance_import_historical_reprocess_api.py
Description: 驗證 Finance historical reprocess Preview 與 Durable Job Bridge accepted command。
"""

from api.routes.finance_import import (
    apply_historical_finance_reprocess,
    preview_historical_finance_reprocess,
)
from api.schemas.finance_import import (
    FinanceImportHistoricalReprocessApplyBody,
    FinanceImportHistoricalReprocessPreviewBody,
)
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from shared_kernel.money import MoneyNTD
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.command_application import DurableJobAcceptance
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessPlan,
    HistoricalReprocessReceipt,
    HistoricalReprocessRow,
)


def _principal():
    return AdminPrincipal(1, "admin", "Admin", "system_admin")


def _owner_selection():
    return [{
        "row_identity": "finance-import-row:1",
        "case_no": "C-1",
        "obligation_identity": "client-obligation:1",
        "reason": "bank memo reviewed",
        "evidence_references": ["review:1"],
    }]


def _plan():
    row = CanonicalFinanceImportRow(
        "finance-import-row:1",
        2,
        MoneyNTD(300),
        FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("a" * 64),
        ("client:1",),
        (),
        ("historical_reprocess_apply",),
    )
    return HistoricalReprocessPlan(
        "batch:1",
        4,
        (
            HistoricalReprocessRow(
                "finance-import-row:1",
                FinanceClassificationType.NON_BUSINESS_REVIEW,
                row,
            ),
        ),
        PreviewFingerprint("b" * 64),
    )


class _Application:
    def __init__(self):
        self.plan = _plan()
        self.request = None
        self.command = None

    def preview(self, batch_identity, correlation_id, _owner_selections=()):
        assert batch_identity == "batch:1"
        assert correlation_id == CorrelationId("preview-1")
        return self.plan

    def apply(self, request):
        self.request = request
        return HistoricalReprocessReceipt(
            request.batch_identity,
            5,
            99,
            1,
            1,
            request.preview_fingerprint,
        )

    def enqueue(self, command):
        self.command = command
        return DurableJobAcceptance(command.job_id, replayed=False)


def test_historical_reprocess_preview_is_a_lossless_typed_plan_projection():
    response = preview_historical_finance_reprocess(
        FinanceImportHistoricalReprocessPreviewBody(
            batch_identity="batch:1", owner_selections=_owner_selection()
        ),
        "preview-1",
        _principal(),
        _Application(),
    )

    assert response.data == {
        "batch_identity": "batch:1",
        "batch_version": 4,
        "row_count": 1,
        "preview_fingerprint": "b" * 64,
    }


def test_historical_reprocess_preview_allows_auto_resolvable_rows_without_selection():
    response = preview_historical_finance_reprocess(
        FinanceImportHistoricalReprocessPreviewBody(batch_identity="batch:1"),
        "preview-1",
        _principal(),
        _Application(),
    )

    assert response.data["row_count"] == 1


def test_historical_reprocess_apply_carries_the_guarded_command_contract():
    application = _Application()
    response = apply_historical_finance_reprocess(
        FinanceImportHistoricalReprocessApplyBody(
            batch_identity="batch:1",
            expected_batch_version=4,
            preview_fingerprint="b" * 64,
            reason="correct historical classification",
            owner_selections=_owner_selection(),
        ),
        "reprocess-1",
        "apply-1",
        _principal(),
        application,
    )

    assert application.command.command_identity == "reprocess-1"
    assert application.command.submitted_by == "admin_user_id:1"
    assert response.data.status_url.endswith(response.data.job_id)


def test_historical_reprocess_apply_enqueues_a_replayable_durable_command():
    class JobApplication:
        def __init__(self):
            self.command = None

        def enqueue(self, command):
            self.command = command
            return DurableJobAcceptance(command.job_id, replayed=False)

    application = JobApplication()
    response = apply_historical_finance_reprocess(
        FinanceImportHistoricalReprocessApplyBody(
            batch_identity="batch:1",
            expected_batch_version=4,
            preview_fingerprint="b" * 64,
            reason="correct historical classification",
            owner_selections=_owner_selection(),
        ),
        "reprocess-1",
        "apply-1",
        _principal(),
        application,
    )

    assert response.data.status_url.endswith(response.data.job_id)
    assert application.command.command_type == "finance_import_historical_reprocess_apply"
    assert application.command.command_identity == "reprocess-1"
    assert application.command.payload["owner_selections"] == _owner_selection()
