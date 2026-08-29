"""Current specs keep preserve-data safety without reviving target-host gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preserve_data_contract_keeps_candidate_and_switch_safety() -> None:
    contract = (
        ROOT
        / "document/架構重整/01_規格基線"
        / "10_Global_保留資料Migration與Cutover_Subsystem.md"
    ).read_text(encoding="utf-8")

    assert "在不修改 source 的前提下" in contract
    assert "建立、驗證並切換至一個新的 candidate database" in contract
    assert "Switch 後必須 restart API、Streamlit、Watcher／worker" in contract


def test_target_host_acceptance_remains_retired() -> None:
    index = (
        ROOT / "document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md"
    ).read_text(encoding="utf-8")

    assert "target-host acceptance 已依決策 53 退役" in index
