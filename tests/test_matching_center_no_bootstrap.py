from pathlib import Path


def test_matching_center_does_not_expose_case_architecture_bootstrap():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")

    assert "ensure_case_architecture_ready" not in source
    assert "CaseArchitectureBootstrapApiClient" not in source


def test_matching_center_reloads_an_active_plan_after_a_streamlit_rerun():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")

    assert "/matching-plans/active" in source
    assert "def _current_matching_plan" in source
