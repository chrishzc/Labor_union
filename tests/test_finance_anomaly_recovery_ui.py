"""UI boundary checks for finance anomaly recovery routing."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_anomaly_center_opens_the_prepopulated_correction_panel() -> None:
    source = (ROOT / "ui/pages/06_finance_alerts.py").read_text(encoding="utf-8")

    assert "render_finance_import_correction_panel" in source
    assert "_select_recovery" in source
    assert "finance_import.correction.v1" in source
    assert "recovery_action_not_supported" in source
    assert "link.preview_endpoint" not in source
    assert "show_manual_actions=False" in source
    assert "government_subsidy.overpayment.disposition.v1" in source
    assert "preview_overpayment_disposition" in source
    assert "apply_overpayment_disposition" in source
    assert "client_finance.over_refund_recovery.matching.v1" in source
    assert "staff_payables.overpayment_recovery.matching.v1" in source
    assert "client_finance.refund_overage.v1" in source
    assert "client_finance.receipt_overage.v1" in source
    assert "_render_client_over_refund_recovery_matching" in source
    assert "_render_client_refund_overage" in source
    assert "_render_client_receipt_overage" in source
    assert "_render_staff_overpayment_recovery_matching" in source


def test_normal_import_page_excludes_the_manual_correction_entrypoint() -> None:
    source = (ROOT / "ui/pages/finance_import/panel.py").read_text(encoding="utf-8")
    panel_body = source.split("def render_finance_import_panel", 1)[1].split(
        "def _render_pending_review_summary", 1
    )[0]

    assert "銀行流水匯入" in panel_body
    assert "_render_manual_correction(client)" not in panel_body
    assert "_render_pending_review_summary(client)" in panel_body
