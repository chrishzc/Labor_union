"""
File: test_finance_import_correction_route.py
Description: 驗證 Finance correction Apply 只透過 Durable Job Bridge 提交 canonical command。
"""

from api.routes.finance_import import apply_finance_import_correction
from api.schemas.finance_import import FinanceImportCorrectionApplyBody
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.command_application import DurableJobAcceptance


class _JobApplication:
    def __init__(self):
        self.command = None

    def enqueue(self, command):
        self.command = command
        return DurableJobAcceptance(command.job_id, replayed=False)


def test_correction_apply_persists_a_durable_command_without_api_background_task():
    application = _JobApplication()
    body = FinanceImportCorrectionApplyBody(
        row_identity="finance-import-row:1",
        classification_type="client_refund_return",
        target_obligation_identities=["refund:C-1"],
        refund_ledger_entry_identity="41",
        allow_partial_refund_recovery=False,
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
        job_application=application,
    )

    assert response.data.status_url.endswith(response.data.job_id)
    assert application.command.command_type == "finance_import_correction_apply"
    assert application.command.command_identity == "correction-key"
    assert application.command.submitted_by == "admin_user_id:1"
    assert application.command.payload["refund_ledger_entry_identity"] == "41"
    assert application.command.payload["allow_partial_refund_recovery"] is False
    assert application.command.payload["target_obligation_identities"] == ["refund:C-1"]
