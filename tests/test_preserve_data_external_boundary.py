"""Current specs keep preserve-data safety without reviving target-host gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preserve_data_contract_keeps_candidate_and_switch_safety() -> None:
    contract = (
        ROOT
        / "document/架構重整/01_規格基線"
        / "10_Global_保留資料Migration與Cutover_Subsystem.md"
    ).read_text(encoding="utf-8")

    assert "在不更動唯讀 source database 的前提下，建立、驗證並切換至新 candidate database" in contract
    assert "切換後重啟 API、管理端前端、Watcher／worker 並完成 read smoke 方標記完成" in contract
    assert "Streamlit" not in contract


def test_target_host_acceptance_remains_retired() -> None:
    deployment = (
        ROOT / "document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md"
    ).read_text(encoding="utf-8")

    assert "本機測試或 rehearsal 通過不構成執行授權" in deployment
    assert "均須取得針對精確 target 的最新人工明確授權" in deployment
