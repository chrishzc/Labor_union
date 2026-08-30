"""Historical matrix text cannot restore a retired target-host gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_matrix_marks_target_host_acceptance_as_retired() -> None:
    source = (
        ROOT / "document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md"
    ).read_text(encoding="utf-8")

    assert "target-host acceptance 已依決策 53 退役" in source
    assert "retired-by-user-2026-08-09" in source


def test_historical_matrix_receipt_is_recoverable_from_the_archive_entry() -> None:
    archive = (
        ROOT / "document/架構重整/04_已完成與上線封存/README.md"
    ).read_text(encoding="utf-8")

    assert "5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65" in archive
    assert "精準取回單一檔案" in archive
