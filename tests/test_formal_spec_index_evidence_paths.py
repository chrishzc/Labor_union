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
    evidence_readme = (
        REPOSITORY_ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "README.md"
    ).read_text(encoding="utf-8")

    assert "document/架構重整/evidence/" not in index_contents
    assert "00_規格書撰寫與生命週期規範.md" in index_contents
    assert "03_追蹤清單與證據" in evidence_readme or "writer_inventory_v3" in evidence_readme or "aggregate receipt" in evidence_readme
    assert (EVIDENCE_DIRECTORY / "writer_inventory_v3").is_dir()
    assert "5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65" in ARCHIVE_README.read_text(
        encoding="utf-8"
    )


def test_formal_spec_index_uses_current_refund_and_deployment_decisions():
    index_contents = SPEC_INDEX_PATH.read_text(encoding="utf-8")
    deployment_contents = (
        REPOSITORY_ROOT
        / "document"
        / "架構重整"
        / "01_規格基線"
        / "18_Global_Deployment與治理正式規格.md"
    ).read_text(encoding="utf-8")
    assert "目前實作仍為 `partial`" not in index_contents
    assert "16_Staff_Payables與Client_Refund正式規格.md" in index_contents
    assert "18_Global_Deployment與治理正式規格.md" in index_contents
    assert "均須取得針對精確 target 的最新人工明確授權" in deployment_contents
    archive_contents = ARCHIVE_README.read_text(encoding="utf-8")
    assert "## 復原基準" in archive_contents
    assert "1f7c9cd7d90895f7846333c48cdb37c95da4caad" in archive_contents
    assert "精準取回單一檔案" in archive_contents
    assert "不要還原整個archive" in archive_contents
