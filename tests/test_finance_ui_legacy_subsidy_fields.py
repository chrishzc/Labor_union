from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def test_order_finance_overview_does_not_display_invalid_subsidy_refund_date():
    source = (ROOT / "ui/pages/order/tab3_finance.py").read_text(encoding="utf-8")

    assert "_derive_subsidy_refund_date" not in source
    assert "補助退款日（衍生公式）" not in source


def test_order_finance_detail_reads_canonical_subsidy_return_obligations():
    source = (ROOT / "ui/pages/order/tab3_finance.py").read_text(encoding="utf-8")

    assert "/client-finance/refund-reversal" in source
    assert "subsidy_return_obligations" in source
    assert 'payment.get("subsidy_return_receivable")' not in source
    assert 'payment.get("subsidy_return_refunded")' not in source


def test_order_finance_detail_keeps_canonical_refunds_visible_without_legacy_summary():
    source = (ROOT / "ui/pages/order/tab3_finance.py").read_text(encoding="utf-8")

    assert "_render_canonical_refunds(refund_detail)" in source
    assert 'get("refund_obligations")' in source
    assert "尚未建立舊客戶帳務摘要" in source


def test_canonical_refunds_render_when_legacy_payment_summary_is_missing(monkeypatch):
    from ui.pages.order import tab3_finance

    rendered = []
    fake_streamlit = SimpleNamespace(
        info=lambda message: rendered.append(("info", message)),
        markdown=lambda message: rendered.append(("markdown", message)),
        dataframe=lambda frame, **_: rendered.append(("dataframe", frame.to_dict("records"))),
    )
    monkeypatch.setattr(tab3_finance, "st", fake_streamlit)

    tab3_finance._render_client_payment_ledger(
        "C-1",
        None,
        {
            "refund_obligations": [
                {"obligation_identity": "refund:C-1", "amount_due_ntd": 300, "due_date": "2026-08-15"}
            ],
            "subsidy_return_obligations": [
                {"obligation_identity": "subsidy:C-1", "amount_due_ntd": 6000, "due_date": "2026-09-15"}
            ],
        },
    )

    assert ("markdown", "#### 一般客戶退款（正式應付）") in rendered
    assert ("markdown", "#### 客戶補助退還（正式應付）") in rendered
    assert any(row[0] == "dataframe" and row[1][0]["義務識別"] == "refund:C-1" for row in rendered)


def test_data_browser_does_not_present_invalid_subsidy_refund_columns_as_business_fields():
    source = (ROOT / "ui/pages/01_data_browser.py").read_text(encoding="utf-8")

    assert '"subsidy_refund_receivable"' not in source
    assert '"subsidy_refund_refunded"' not in source
