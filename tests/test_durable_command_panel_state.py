from types import SimpleNamespace

from ui.pages.finance_import.panel import _batch_apply_command
from ui.pages.scheduling.assignment_plan_panel import _apply_command
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_assignment_plan_reuses_the_original_command_snapshot_until_terminal():
    state = {}
    preview = SimpleNamespace(preview_fingerprint="preview-a")
    segments = [{"staff_id": 9, "official_service_dates": ["2026-08-08"]}]

    first = _apply_command("CASE-1", preview, segments, "confirmed", state)
    repeated = _apply_command("CASE-1", object(), [], "changed", state)

    assert repeated is first
    assert repeated["preview"] is preview
    assert repeated["segments"] == segments
    assert repeated["reason"] == "confirmed"
    assert repeated["idempotency_key"].startswith("assignment-plan-apply-CASE-1-")


def test_assignment_plan_creates_a_new_command_only_after_terminal_status():
    state = {}
    first = _apply_command("CASE-1", object(), [], "confirmed", state)
    first["terminal"] = True

    replacement = _apply_command("CASE-1", object(), [], "new preview", state)

    assert replacement is not first
    assert replacement["reason"] == "new preview"
    assert replacement["idempotency_key"] != first["idempotency_key"]


def test_finance_batch_reuses_the_same_apply_identity_while_non_terminal():
    state = {}
    preview = SimpleNamespace(
        batch_identity="finance-import-batch:1",
        preview_fingerprint="preview-a",
    )

    first = _batch_apply_command(state, preview, "confirmed")
    repeated = _batch_apply_command(state, preview, "changed")

    assert repeated is first
    assert repeated["reason"] == "confirmed"
    assert repeated["idempotency_key"].startswith("finance-import-apply:")


def test_pending_durable_commands_use_bounded_fragment_polling():
    finance_panel = (ROOT / "ui/pages/finance_import/panel.py").read_text(encoding="utf-8")
    assignment_panel = (ROOT / "ui/pages/scheduling/assignment_plan_panel.py").read_text(encoding="utf-8")

    assert "@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)" in finance_panel
    assert "@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)" in assignment_panel
