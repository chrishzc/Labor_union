from types import SimpleNamespace

from ui.pages.scheduling import matching_center


def test_matching_center_uses_backend_bypass_principal(monkeypatch):
    monkeypatch.setattr(matching_center, "admin_auth_is_bypassed", lambda: True)
    monkeypatch.setattr(
        matching_center,
        "st",
        SimpleNamespace(session_state={"line_admin_profile": {"username": "other-user"}}),
    )

    assert matching_center._actor() == "development-bypass"


def test_matching_center_uses_signed_in_username(monkeypatch):
    monkeypatch.setattr(matching_center, "admin_auth_is_bypassed", lambda: False)
    monkeypatch.setattr(
        matching_center,
        "st",
        SimpleNamespace(session_state={"line_admin_profile": {"username": "admin-user"}}),
    )

    assert matching_center._actor() == "admin-user"


def test_single_caregiver_plan_payload_leaves_segment_order_to_the_workflow():
    source = __import__("pathlib").Path(matching_center.__file__).read_text(encoding="utf-8")

    single_caregiver_section = source[source.index("def _render_single_caregiver_matching"):source.index("def _render_single_caregiver_contact")]
    assert '"segment_order": 1' not in single_caregiver_section
