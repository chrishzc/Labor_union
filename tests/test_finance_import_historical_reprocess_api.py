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

    assert application.request.idempotency_key.value == "reprocess-1"
    assert application.request.actor.actor_id == "admin"
    assert response.data["reprocess_run_id"] == 99
    assert response.data["resulting_batch_version"] == 5


def test_historical_reprocess_apply_enqueues_a_replayable_durable_command():
    class JobRepository:
        def __init__(self):
            self.command = None

        def enqueue_command(self, command):
            self.command = command
            return command.job_id

    repository = JobRepository()
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
        repository,
    )

    assert response.data.status_url.endswith(response.data.job_id)
    assert repository.command.command_type == "finance_import_historical_reprocess_apply"
    assert repository.command.command_identity == "reprocess-1"
    assert repository.command.payload["owner_selections"] == _owner_selection()
