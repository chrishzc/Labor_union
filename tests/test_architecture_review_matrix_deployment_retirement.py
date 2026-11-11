"""Retired architecture review matrix and target-host gate cannot be restored."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_matrix_marks_target_host_acceptance_as_retired() -> None:
    index = (
        ROOT / "document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md"
    ).read_text(encoding="utf-8")
    deployment = (
        ROOT / "document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md"
    ).read_text(encoding="utf-8")

    assert "11 架構總審矩陣" not in index
    assert "[18_Global_Deployment與治理正式規格.md](18_Global_Deployment與治理正式規格.md)" in index
    assert "本機測試或 rehearsal 通過不構成執行授權" in deployment


def test_historical_matrix_receipt_is_recoverable_from_the_archive_entry() -> None:
    archive = (
        ROOT / "document/架構重整/04_已完成與上線封存/README.md"
    ).read_text(encoding="utf-8")

    assert "5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65" in archive
    assert "精準取回單一檔案" in archive
