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


def test_current_ssot_keeps_target_host_retired_and_history_recoverable() -> None:
    index = (
        ROOT / "document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md"
    ).read_text(encoding="utf-8")
    archive = (
        ROOT / "document/架構重整/04_已完成與上線封存/README.md"
    ).read_text(encoding="utf-8")

    assert "target-host acceptance 已依決策 53 退役" in index
    assert "preserve-data" in index
    assert "精準取回單一檔案" in archive
