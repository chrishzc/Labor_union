import io
import os
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from api.main import app
from api.schemas.line_config import LineMenusConfig, RichMenuDefinition
from services.db_service import get_connection
from services.json_config_service import read_config
from services.line_rich_menu_service import (
    _complete_publication,
    _publish_to_line,
    create_publication_job,
    get_current_rich_menu_id,
    get_publication,
)
from services.media_storage_service import (
    MediaValidationError,
    get_media_asset,
    media_storage_root,
    normalize_uploaded_rich_menu_image,
    render_rich_menu_image,
    store_generated_rich_menu_image,
)


ROOT = Path(__file__).resolve().parents[1]


def _cleanup(
    publication_id: int | None,
    asset_id: int | None,
    user_id: str | None,
    restore_current_ids: list[int] | None = None,
) -> None:
    storage_path = None
    if asset_id:
        try:
            asset = get_media_asset(asset_id)
            storage_path = media_storage_root() / asset["storage_key"]
        except Exception:
            pass
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if publication_id:
                cursor.execute(
                    "DELETE FROM line_tasks WHERE idempotency_key LIKE %s",
                    (f"rich-menu-publication:{publication_id}:%",),
                )
                cursor.execute(
                    "DELETE FROM line_rich_menu_publications WHERE id=%s",
                    (publication_id,),
                )
            if user_id:
                cursor.execute("DELETE FROM line_users WHERE line_user_id=%s", (user_id,))
            if asset_id:
                cursor.execute("DELETE FROM media_assets WHERE id=%s", (asset_id,))
            if restore_current_ids:
                placeholders = ",".join(["%s"] * len(restore_current_ids))
                cursor.execute(
                    f"UPDATE line_rich_menu_publications SET is_current=TRUE WHERE id IN ({placeholders})",
                    restore_current_ids,
                )
        conn.commit()
    finally:
        conn.close()
    if storage_path:
        storage_path.unlink(missing_ok=True)


def test_three_role_menu_config_and_generated_preview():
    config = read_config("line_menus", LineMenusConfig)
    assert {menu.audience_role for menu in config.menus} == {
        "customer",
        "staff",
        "union_staff",
    }
    union_menu = next(menu for menu in config.menus if menu.audience_role == "union_staff")
    content = render_rich_menu_image(union_menu.model_dump(mode="json"))
    with Image.open(io.BytesIO(content)) as image:
        assert image.size == (2500, 843)
        assert image.format == "JPEG"
    assert len(content) <= 1024 * 1024


def test_menu_validation_rejects_overlap_and_unsafe_uri():
    config = read_config("line_menus", LineMenusConfig)
    payload = config.menus[0].model_dump(mode="json")
    payload["buttons"][1]["bounds"]["x"] = 1000
    try:
        RichMenuDefinition.model_validate(payload)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("overlapping buttons must be rejected")

    payload = config.menus[0].model_dump(mode="json")
    payload["buttons"][0]["action"] = {
        "type": "uri",
        "uri_source": "literal",
        "uri": "javascript:alert(1)",
        "text": None,
        "data": None,
    }
    try:
        RichMenuDefinition.model_validate(payload)
    except ValueError as exc:
        assert "http or https" in str(exc)
    else:
        raise AssertionError("unsafe URI scheme must be rejected")


def test_uploaded_image_validation_checks_real_dimensions():
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(output, format="PNG")
    try:
        normalize_uploaded_rich_menu_image(
            output.getvalue(), expected_width=2500, expected_height=843
        )
    except MediaValidationError as exc:
        assert "2500x843" in str(exc)
    else:
        raise AssertionError("wrong image dimensions must be rejected")


def test_line_menu_state_rejects_stale_revision():
    old = {name: os.environ.get(name) for name in ("APP_ENV", "ENABLE_ADMIN_AUTH", "INTERNAL_API_KEY")}
    os.environ["APP_ENV"] = "development"
    os.environ["ENABLE_ADMIN_AUTH"] = "false"
    os.environ["INTERNAL_API_KEY"] = "stage-5-4-test-key"
    client = TestClient(app)
    headers = {"X-Internal-API-Key": "stage-5-4-test-key"}
    try:
        state = client.get("/api/config/line-menus/state", headers=headers)
        assert state.status_code == 200
        response = client.put(
            "/api/config/line-menus",
            headers={**headers, "If-Match": "0" * 64},
            json=state.json()["config"],
        )
        assert response.status_code == 409
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_rich_menu_upload_and_publish_api_in_development_bypass():
    config = read_config("line_menus", LineMenusConfig)
    menu = next(item for item in config.menus if item.id == "default_menu")
    image = render_rich_menu_image(menu.model_dump(mode="json"))
    old = {
        name: os.environ.get(name)
        for name in ("APP_ENV", "ENABLE_ADMIN_AUTH", "INTERNAL_API_KEY")
    }
    os.environ["APP_ENV"] = "development"
    os.environ["ENABLE_ADMIN_AUTH"] = "false"
    os.environ["INTERNAL_API_KEY"] = "stage-5-4-api-key"
    headers = {"X-Internal-API-Key": "stage-5-4-api-key"}
    client = TestClient(app)
    publication_id = None
    asset_id = None
    try:
        uploaded = client.post(
            "/api/v1/line/rich-menus/default_menu/images",
            headers=headers,
            files={"image": ("menu.png", image, "image/jpeg")},
        )
        assert uploaded.status_code == 200
        asset_id = int(uploaded.json()["data"]["id"])
        published = client.post(
            "/api/v1/line/rich-menus/default_menu/publish",
            headers=headers,
            json={"reason": "integration test"},
        )
        assert published.status_code == 202
        publication_id = int(published.json()["data"]["id"])
    finally:
        _cleanup(publication_id, asset_id, None)
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_publication_completion_relinks_matching_role():
    config = read_config("line_menus", LineMenusConfig)
    menu = next(item for item in config.menus if item.audience_role == "staff")
    user_id = f"U-stage-5-4-{uuid.uuid4().hex}"
    publication_id = None
    asset_id = None
    previous_current_ids: list[int] = []
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM line_rich_menu_publications WHERE audience_role='staff' AND is_current=TRUE"
            )
            previous_current_ids = [
                int(row.get("id") if isinstance(row, dict) else row[0])
                for row in cursor.fetchall()
            ]
            cursor.execute(
                "INSERT INTO line_users (line_user_id,status,role) VALUES (%s,'active','staff')",
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()
    try:
        publication = create_publication_job(menu.id, None)
        publication_id = int(publication["id"])
        asset = store_generated_rich_menu_image(
            menu.model_dump(mode="json"), created_by_admin_user_id=None
        )
        asset_id = int(asset["id"])
        with patch("services.line_rich_menu_service._write_legacy_id"):
            _complete_publication(publication, "richmenu-stage-5-4", asset_id)
        completed = get_publication(publication_id)
        assert completed["status"] == "published"
        assert completed["is_current"] == 1
        assert get_current_rich_menu_id("staff") == "richmenu-stage-5-4"
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(1) AS total FROM line_tasks WHERE idempotency_key=%s",
                    (f"rich-menu-publication:{publication_id}:{user_id}",),
                )
                row = cursor.fetchone()
                total = row.get("total") if isinstance(row, dict) else row[0]
            assert total == 1
        finally:
            conn.close()
    finally:
        _cleanup(publication_id, asset_id, user_id, previous_current_ids)


def test_publish_boundary_uses_mocked_line_calls_only():
    config = read_config("line_menus", LineMenusConfig)
    menu = next(item for item in config.menus if item.audience_role == "staff")
    item = {
        "id": 999999,
        "config_snapshot": menu.model_dump(mode="json"),
        "requested_by_admin_user_id": None,
    }
    asset_id = None
    old_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "test-token-never-sent"
    created = Mock(ok=True)
    created.json.return_value = {"richMenuId": "richmenu-mocked"}
    uploaded = Mock(ok=True)
    try:
        with patch(
            "services.line_rich_menu_service.requests.request",
            side_effect=[created, uploaded],
        ) as request_mock:
            rich_menu_id, asset_id = _publish_to_line(item)
        assert rich_menu_id == "richmenu-mocked"
        assert request_mock.call_count == 2
    finally:
        if old_token is None:
            os.environ.pop("LINE_CHANNEL_ACCESS_TOKEN", None)
        else:
            os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = old_token
        _cleanup(None, asset_id, None)


def test_rich_menu_ui_has_no_fixed_polling():
    source = (ROOT / "ui/components/line_rich_menu_manager.py").read_text(encoding="utf-8")
    page = (ROOT / "ui/pages/07_line_management.py").read_text(encoding="utf-8")
    assert "time.sleep" not in source
    assert "autorefresh" not in source.lower()
    assert "render_rich_menu_manager(client, token, profile)" in page


def test_rich_menu_manager_hides_line_engineering_fields():
    source = (ROOT / "ui/components/line_rich_menu_manager.py").read_text(encoding="utf-8")

    assert "LINE Menu ID" not in source
    assert "Postback Data" not in source
    assert "儲存草稿" not in source
