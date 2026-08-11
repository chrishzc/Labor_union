"""Regression coverage for canonical LIFF identity entrypoints."""

from pathlib import Path

from scripts import run_line_worker


ROOT = Path(__file__).resolve().parents[3]


def test_identity_flow_url_uses_supported_liff_additional_information_format(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbCdEf")

    url = run_line_worker._identity_flow_url("admin_binding", "flow with spaces")

    assert url == (
        "https://liff.line.me/1234567890-AbCdEf/"
        "?purpose=admin_binding&flow_id=flow+with+spaces"
    )


def test_identity_page_reads_flow_context_after_liff_initialization() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    initialize_source = source.split("async function initialize()", 1)[1]

    initialization = initialize_source.index("await liff.init")
    context_read = initialize_source.index("readIdentityFlowContext()")

    assert initialization < context_read
    assert 'location.assign("/line-registration")' in source


def test_default_order_query_menu_uses_message_action() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")

    assert '"type": "message"' in source
    assert '"text": "訂單查詢"' in source


def test_registration_page_uses_only_canonical_identity_endpoints() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in source
    assert "/api/v1/line/identity/registration/apply" in source
    assert "/api/line/register" not in source
    assert "/api/line/config" not in source
