from pathlib import Path


def test_matching_center_does_not_expose_case_architecture_bootstrap():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")

    assert "ensure_case_architecture_ready" not in source
    assert "CaseArchitectureBootstrapApiClient" not in source


def test_matching_center_reloads_an_active_plan_after_a_streamlit_rerun():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")

    assert "/matching-plans/active" in source
    assert "def _current_matching_plan" in source


def test_single_caregiver_matching_uses_the_candidate_contact_pool_before_a_plan():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")
    section = source[
        source.index("def _render_single_caregiver_matching"):
        source.index("def _render_single_caregiver_contact")
    ]

    assert "_render_candidate_contact_pool(target_case_no, candidates)" in section
    assert '"聯繫與確認意願"' not in section
    assert 'f"/api/v1/orders/{target_case_no}/matching-plans"' not in section


def test_candidate_contact_pool_preserves_each_candidate_flow_and_gates_plan_creation():
    source = Path("ui/pages/scheduling/matching_center.py").read_text(encoding="utf-8")

    assert "/candidate-contact-pool/candidates" in source
    assert "/information" in source
    assert "/willingness" in source
    assert 'item.get("willingness") == "willing"' in source
    assert "_create_formal_plan_from_willing_candidate" in source
