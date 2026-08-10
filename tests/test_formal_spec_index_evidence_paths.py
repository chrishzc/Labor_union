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


def test_formal_spec_index_references_the_managed_evidence_directory():
    index_contents = SPEC_INDEX_PATH.read_text(encoding="utf-8")

    assert "document/架構重整/evidence/" not in index_contents
    assert "document/架構重整/03_追蹤清單與證據/evidence/" in index_contents
    assert (EVIDENCE_DIRECTORY / "architecture_approval_2026-08-03.json").is_file()
    assert (EVIDENCE_DIRECTORY / "writer_inventory_v2" / "README.md").is_file()


def test_formal_spec_index_uses_current_refund_and_deployment_decisions():
    index_contents = SPEC_INDEX_PATH.read_text(encoding="utf-8")
    completion_receipt = (
        EVIDENCE_DIRECTORY
        / "2026-08-09_staff_payables_client_refund_formal_spec_revalidation_receipt.md"
    ).read_text(encoding="utf-8")

    assert "目前實作仍為 `partial`" not in index_contents
    assert "proven-current-evidence" in completion_receipt
    assert "retired-by-user-2026-08-09" in index_contents
    assert "決策 53" in index_contents

    revalidation_receipt = (
        EVIDENCE_DIRECTORY / "2026-08-09_formal_spec_index_revalidation_receipt.md"
    ).read_text(encoding="utf-8")
    assert "`46` 保留 deployment acceptance" not in revalidation_receipt
    assert "target-host\n  deployment acceptance 退役" in revalidation_receipt
