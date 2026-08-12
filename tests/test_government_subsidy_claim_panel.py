"""Prevent the first claim plan from being hidden behind a batch lookup."""

from pathlib import Path


CLAIM_PANEL = Path("ui/pages/government_subsidy/claim_panel.py")


def test_claim_planning_renders_before_existing_batch_is_required() -> None:
    source = CLAIM_PANEL.read_text(encoding="utf-8")

    planning_position = source.index("_render_planning_panel(client)")
    batch_lookup_position = source.index("batch = st.session_state.get(_BATCH_STATE_KEY)")

    assert planning_position < batch_lookup_position


def test_claim_apply_reuses_the_preview_command_after_terminal_status() -> None:
    source = CLAIM_PANEL.read_text(encoding="utf-8")

    assert 'if isinstance(existing, dict):\n        return existing' in source
    assert 'and not existing.get("terminal")' not in source
