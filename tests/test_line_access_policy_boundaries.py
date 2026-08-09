"""Regression checks for the human-approved LINE and administrator session policies."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from subsystems.access.authentication_session import _session_expiry


ROOT = Path(__file__).resolve().parents[1]


def test_line_review_queue_has_no_expiry_or_automatic_decision_policy() -> None:
    workflow = (ROOT / "subsystems/line/identity_review_workflow.py").read_text(encoding="utf-8")
    ui = (ROOT / "ui/components/line_review_manager.py").read_text(encoding="utf-8")

    assert "LINE_REVIEW_STALE_HOURS" not in workflow
    assert "stale_pending" not in workflow
    assert "逾 " not in ui
    assert "ORDER BY {order_sql}" in workflow


def test_rich_menu_apply_requires_matching_server_preview_receipt() -> None:
    workflow = (ROOT / "subsystems/line/rich_menu_publication_workflow.py").read_text(encoding="utf-8")
    route = (ROOT / "api/routes/line_rich_menus.py").read_text(encoding="utf-8")
    ui = (ROOT / "ui/components/line_rich_menu_manager.py").read_text(encoding="utf-8")

    assert "def create_publication_preview" in workflow
    assert "previewed_by_admin_user_id" in workflow
    assert "config_fingerprint" in workflow
    assert "publication_id IS NULL" in workflow
    assert '"/{menu_id}/publish-preview"' in route
    assert "preview_id=payload.preview_id" in route
    assert "確認目前預覽，繼續套用" in ui


def test_session_expiry_is_sliding_but_never_exceeds_eight_hour_login_deadline() -> None:
    login_at = datetime(2026, 8, 9, 9, 0, 0)
    deadline = login_at + timedelta(hours=8)

    assert _session_expiry(login_at, deadline) == login_at + timedelta(minutes=30)
    assert _session_expiry(deadline - timedelta(minutes=10), deadline) == deadline

    source = (ROOT / "subsystems/access/authentication_session.py").read_text(encoding="utf-8")
    assert "ADMIN_SESSION_IDLE_MINUTES = 30" in source
    assert "ADMIN_SESSION_MAXIMUM_MINUTES = 8 * 60" in source
    assert "s.absolute_expires_at > UTC_TIMESTAMP()" in source
