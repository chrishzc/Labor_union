"""Guard the formal Staff Payables and Client Refund legacy boundaries."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_finance_center_owns_formal_payment_workspaces() -> None:
    source = (ROOT / "ui/pages/04_finance.py").read_text(encoding="utf-8")

    assert "tab3_finance" not in source
    assert "💰 帳務作業中心" in source
    assert "FINANCE_WORKSPACES" in source
    assert "_render_staff_payout_workspace" in source
    assert "_render_accounts_payable_workspace" in source


def test_client_payment_snapshot_has_no_production_caller() -> None:
    production_roots = ("api", "domains", "infrastructure", "line", "scripts", "services", "subsystems", "ui")
    caller_paths = []
    for root_name in production_roots:
        for source_path in (ROOT / root_name).rglob("*.py"):
            if source_path == ROOT / "subsystems/client_finance/payment_snapshot.py":
                continue
            if "create_client_payment_snapshot" in source_path.read_text(encoding="utf-8"):
                caller_paths.append(source_path)

    assert caller_paths == []


def test_current_receipt_keeps_only_preserve_data_as_external_gate() -> None:
    receipt = (
        ROOT
        / "document/架構重整/03_追蹤清單與證據/evidence"
        / "2026-08-09_staff_payables_client_refund_formal_spec_revalidation_receipt.md"
    ).read_text(encoding="utf-8")

    assert "target-host\n部署驗收已依決策 53 退役" in receipt
    assert "preserve-data hard rehearsal 仍是 Global external gate" in receipt
