"""Regression guard for the retired legacy Staff Payables transfer writer."""

from pathlib import Path


def test_legacy_transfer_reconciliation_writer_is_removed() -> None:
    project_root = Path(__file__).parents[1]
    retired_writer = (
        project_root
        / "subsystems"
        / "staff_payables"
        / "actual_transfer_reconciliation.py"
    )

    assert not retired_writer.exists()

    production_roots = ("api", "domains", "infrastructure", "scripts", "services", "subsystems", "ui")
    production_sources = (
        source_path
        for root_name in production_roots
        for source_path in (project_root / root_name).rglob("*.py")
    )
    source_text = "\n".join(
        source_path.read_text(encoding="utf-8") for source_path in production_sources
    )

    assert "actual_transfer_reconciliation" not in source_text
    assert "reconcile_staff_actual_transfer" not in source_text
