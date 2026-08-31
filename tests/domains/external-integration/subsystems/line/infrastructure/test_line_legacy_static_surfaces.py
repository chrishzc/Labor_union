"""
File: test_line_legacy_static_surfaces.py
Description: 驗證直接靜態舊入口不再繞過 canonical LIFF 身分與異動契約。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app


def test_static_bind_redirects_to_canonical_identity_and_preserves_navigation_query() -> None:
    response = TestClient(app).get(
        "/static/bind.html?userId=U-navigation-only&target=staff_schedule",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/line-identity?userId=U-navigation-only&target=staff_schedule"
    )


def test_profile_update_static_uses_verified_liff_preview_and_apply_contract() -> None:
    source = Path("line/static/profile_update.html").read_text(encoding="utf-8")

    assert "預覽異動" in source
    assert "確認並送出申請" in source
    assert 'id="submitButton" disabled' in source
    assert "/api/v1/line/client-profile/query" in source
    assert "/api/v1/line/client-profile/preview" in source
    assert "/api/v1/line/client-profile/apply" in source
    assert "line_user_id" not in source
    assert "liff.getProfile" not in source
    assert "liff.getIDToken" in source
