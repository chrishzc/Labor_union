from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPEC_INDEX_PATH = (
    REPOSITORY_ROOT
    / "document"
    / "架構重整"
    / "01_規格基線"
    / "15_正式規格索引與裁決總表.md"
)
EVIDENCE_DIRECTORY = REPOSITORY_ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence"
ARCHIVE_README = (
    REPOSITORY_ROOT / "document" / "架構重整" / "04_已完成與上線封存" / "README.md"
)


def test_formal_spec_index_references_the_managed_evidence_directory():
    index_contents = SPEC_INDEX_PATH.read_text(encoding="utf-8")

    assert "document/架構重整/evidence/" not in index_contents
    assert "document/架構重整/03_追蹤清單與證據/evidence/" in index_contents
    assert "04_已完成與上線封存/README.md" in index_contents
    assert (EVIDENCE_DIRECTORY / "writer_inventory_v3").is_dir()
    assert "5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65" in ARCHIVE_README.read_text(
        encoding="utf-8"
    )


def test_formal_spec_index_uses_current_refund_and_deployment_decisions():
    index_contents = SPEC_INDEX_PATH.read_text(encoding="utf-8")
    assert "目前實作仍為 `partial`" not in index_contents
    assert "retired-by-user-2026-08-09" in index_contents
    assert "決策 53" in index_contents
    assert "target-host acceptance 已依決策 53 退役" in index_contents
    archive_contents = ARCHIVE_README.read_text(encoding="utf-8")
    assert "## 復原基準" in archive_contents
    assert "1f7c9cd7d90895f7846333c48cdb37c95da4caad" in archive_contents
    assert "精準取回單一檔案" in archive_contents
    assert "不要還原整個archive" in archive_contents
