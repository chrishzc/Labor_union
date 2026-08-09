"""Repeatable static checks for the LINE artificial review workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_ui_has_no_fixed_polling():
    source = (ROOT / "ui" / "components" / "line_review_manager.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "ui" / "pages" / "07_line_management.py").read_text(
        encoding="utf-8"
    )
    assert "time.sleep" not in source
    assert "autorefresh" not in source.lower()
    assert "render_review_manager(client, token, profile)" in page


def test_schema_contains_reviewer_metadata_and_replayable_migration():
    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    migration = (
        ROOT / "db" / "schema_parts" / "97_line_confirmation_review.sql"
    ).read_text(encoding="utf-8")
    assert "reviewed_by_admin_user_id" in schema
    assert "decision_reason" in schema
    assert "INFORMATION_SCHEMA.COLUMNS" in migration
    assert "fk_confirmation_admin_reviewer" in migration


def test_review_manager_hides_raw_line_identifier_labels():
    source = (ROOT / "ui/components/line_review_manager.py").read_text(encoding="utf-8")

    assert "LINE User ID" not in source
