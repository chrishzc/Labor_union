"""Historical matrix text cannot restore a retired target-host gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_matrix_marks_target_host_acceptance_as_retired() -> None:
    source = (
        ROOT / "document/架構重整/01_規格基線/11_架構總審矩陣與實作切片.md"
    ).read_text(encoding="utf-8")

    assert "已由決策 53 退役" in source
    assert "實際部署\nprotocol／latency evidence" not in source


def test_historical_matrix_receipt_does_not_keep_target_host_external_gate() -> None:
    receipt = (
        ROOT
        / "document/架構重整/03_追蹤清單與證據/evidence"
        / "2026-08-09_architecture_review_matrix_revalidation_receipt.md"
    ).read_text(encoding="utf-8")

    assert "target-host deployment、TLS／\n  HTTP2／latency、worker recovery 等 external" not in receipt
    assert "target-host deployment、\n  TLS／HTTP2／latency acceptance 已退役" in receipt
