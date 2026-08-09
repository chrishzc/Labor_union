"""Route contract for durable Finance Import correction submission."""

from api.routes.finance_import import apply_finance_import_correction
from api.schemas.finance_import import FinanceImportCorrectionApplyBody
from subsystems.access.authentication_session import AdminPrincipal


class _JobRepository:
    def __init__(self):
        self.command = None

    def enqueue_command(self, command):
        self.command = command
        return command.job_id


def test_correction_apply_persists_a_durable_command_without_api_background_task():
    repository = _JobRepository()
    body = FinanceImportCorrectionApplyBody(
        row_identity="finance-import-row:1",
        classification_type="client_refund_return",
        target_obligation_identities=["refund:C-1"],
        refund_ledger_entry_identity="41",
        reason="銀行退匯已核對",
        evidence=["bank-return-notice"],
        expected_batch_version=3,
        expected_canonical_fact_version=4,
        expected_alert_version=5,
        preview_fingerprint="a" * 64,
    )

    response = apply_finance_import_correction(
        body=body,
        idempotency_key="correction-key",
        correlation_id="correction-correlation",
        principal=AdminPrincipal(1, "admin", "Admin", "system_admin"),
        job_repository=repository,
    )

    assert response.data.status_url.endswith(response.data.job_id)
    assert repository.command.command_type == "finance_import_correction_apply"
    assert repository.command.command_identity == "correction-key"
    assert repository.command.payload["refund_ledger_entry_identity"] == "41"
    assert repository.command.payload["target_obligation_identities"] == ["refund:C-1"]
