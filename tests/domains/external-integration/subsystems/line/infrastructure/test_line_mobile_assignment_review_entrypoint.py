"""Verify LINE mobile assignment-review entry routing."""

from pathlib import Path


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_gateway_and_mobile_admin_use_canonical_liff_config_without_url_identity_bypass() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    mobile_admin = (ROOT / "line" / "static" / "mobile_admin.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in gateway
    assert "/api/v1/line/identity/runtime-config" in mobile_admin
    assert "/api/line/config" not in gateway
    assert "/api/config/liff/runtime" not in gateway
    assert "urlUserId" not in gateway
    assert "?userId=" not in gateway
    assert "/api/line/config" not in mobile_admin


def test_identity_page_routes_mobile_admin_targets_without_opening_staff_flow() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    mobile_admin_route = source.split("function requestedMobileAdminPage()", 1)[1].split(
        "function hasSensitiveFlowContext()", 1
    )[0]
    initialize_source = source.split("async function initialize()", 1)[1]

    assert 'customer_service: "/line-mobile-admin?target=customer_service"' in mobile_admin_route
    assert 'scheduling_review: "/line-mobile-admin?target=scheduling_review"' in mobile_admin_route
    assert 'staff_review: "/line-mobile-admin?target=staff_review"' in mobile_admin_route
    assert "location.replace(mobileAdminPage);" in initialize_source
    assert initialize_source.index("location.replace(mobileAdminPage);") < initialize_source.index(
        "openStaffPage(staffPage)"
    )
