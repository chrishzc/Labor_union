"""The former direct subsidy reconciliation writer must stay retired."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_government_subsidy_reconciliation_writer_is_removed() -> None:
    retired_module = ROOT / "subsystems/government_subsidy/receipt_reconciliation.py"
    assert not retired_module.exists()

    production_roots = ("api", "domains", "infrastructure", "line", "scripts", "services", "subsystems", "ui")
    source_text = "\n".join(
        source_path.read_text(encoding="utf-8")
        for root_name in production_roots
        for source_path in (ROOT / root_name).rglob("*.py")
    )
    assert "reconcile_government_subsidy" not in source_text
    assert "government_subsidy.receipt_reconciliation" not in source_text
