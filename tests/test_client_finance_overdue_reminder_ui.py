from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_case_refund_panel_shows_loading_and_keeps_bank_rows_outside_case_page() -> None:
    source = (ROOT / "ui/pages/order/client_refund_reversal_panel.py").read_text(
        encoding="utf-8"
    )

    assert 'with st.spinner("正在載入正式退款與補助退還根事實…")' in source
    assert "銀行出款、退匯與套用須從「銀行流水匯入與帳務修正」進入" in source
    assert "facts.refund_obligations" in source
    assert "facts.subsidy_return_obligations" in source


def test_finance_import_correction_is_the_only_ui_entry_for_bank_settlement_types() -> None:
    source = (ROOT / "ui/pages/finance_import/panel.py").read_text(encoding="utf-8")

    assert '"client_refund"' in source
    assert '"client_subsidy_return"' in source
    assert '"client_refund_return"' in source
    assert 'with st.spinner("正在受理人工修正工作…")' in source
    assert "_JOB_STATUS_POLL_INTERVAL_SECONDS" in source


def test_anomaly_center_exposes_all_read_only_overdue_review_codes() -> None:
    source = (ROOT / "ui/pages/06_finance_alerts.py").read_text(encoding="utf-8")

    assert '_OVERDUE_CODES = {"RECEIVABLE-001", "CLIENTPAYABLE-001", "RETURN-001", "SUBSIDYADVANCE-001"}' in source
