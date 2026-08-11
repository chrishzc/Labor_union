"""
================================================================================
檔案名稱: services/line_rich_menu_service.py
功能說明: LINE 下方選單可靠發布服務，管理圖片、版本、發布狀態、重試與使用者綁定
================================================================================
"""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
import requests

from api.schemas.line_config import LineMenusConfig, RichMenuDefinition
from domains.line.configuration import LineConfigurationKind
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.delivery_task_workflow import enqueue_line_task
from subsystems.line.message_configuration import configuration_definition
from subsystems.line.media_archive import (
    MediaValidationError,
    get_media_asset,
    read_media_asset,
    store_generated_rich_menu_image,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_IDS_PATH = PROJECT_ROOT / "config" / "rich_menu_ids.json"
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


class RichMenuPublicationNotFoundError(LookupError):
    pass


class RichMenuPublicationConflictError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "rich_menu_publication_conflict",
    ) -> None:
        super().__init__(message)
        self.code = code


class RichMenuPublishError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _decode_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _current_menu_configuration() -> tuple[LineMenusConfig, str]:
    with open_line_unit_of_work() as unit_of_work:
        configuration_snapshot = unit_of_work.configurations.get(
            LineConfigurationKind.RICH_MENUS
        )
    configuration = LineMenusConfig.model_validate(
        configuration_definition(configuration_snapshot)
    )
    return configuration, str(configuration_snapshot.revision.value)


def _current_menu_snapshot(menu_id: str) -> tuple[RichMenuDefinition, str, str]:
    config, revision = _current_menu_configuration()
    menu = next((item for item in config.menus if item.id == menu_id), None)
    if not menu:
        raise RichMenuPublicationNotFoundError(f"找不到 Rich Menu {menu_id}")
    if not menu.enabled:
        raise RichMenuPublicationConflictError("停用中的 Rich Menu 不能發布")
    if menu.appearance.image_mode == "uploaded":
        if not menu.appearance.image_asset_id:
            raise RichMenuPublicationConflictError("上傳圖片模式尚未選擇圖片資產")
        asset = get_media_asset(menu.appearance.image_asset_id)
        if (asset.get("width"), asset.get("height")) != (
            menu.size.width,
            menu.size.height,
        ):
            raise RichMenuPublicationConflictError("圖片尺寸與 Rich Menu 尺寸不一致")
    menu_snapshot = menu.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(menu_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return menu, revision, fingerprint


def create_publication_preview(menu_id: str, previewed_by_admin_user_id: int | None) -> dict[str, Any]:
    if previewed_by_admin_user_id is None:
        raise RichMenuPublicationConflictError(
            "發布預覽需要已登入的管理員",
            code="authenticated_admin_required",
        )
    menu, revision, fingerprint = _current_menu_snapshot(menu_id)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO line_rich_menu_publish_previews (
                    menu_config_id, config_revision, config_fingerprint,
                    previewed_by_admin_user_id
                ) VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), previewed_at=UTC_TIMESTAMP()
                """,
                (menu.id, revision, fingerprint, previewed_by_admin_user_id),
            )
            preview_id = int(cursor.lastrowid)
        conn.commit()
        return {"preview_id": preview_id, "config_revision": revision, "config_fingerprint": fingerprint}
    finally:
        conn.close()


def validate_publication_preview(
    menu_id: str,
    preview_id: int,
    previewed_by_admin_user_id: int | None,
) -> dict[str, Any]:
    if previewed_by_admin_user_id is None:
        raise RichMenuPublicationConflictError(
            "發布需要已登入的管理員",
            code="authenticated_admin_required",
        )
    _, revision, fingerprint = _current_menu_snapshot(menu_id)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT id FROM line_rich_menu_publish_previews
                WHERE id=%s AND menu_config_id=%s AND config_revision=%s
                  AND config_fingerprint=%s AND previewed_by_admin_user_id=%s
                  AND publication_id IS NULL
                  AND canonical_publication_task_id IS NULL
                """,
                (
                    preview_id, menu_id, revision, fingerprint,
                    previewed_by_admin_user_id,
                ),
            )
            if cursor.fetchone() is None:
                raise RichMenuPublicationConflictError(
                    "請先預覽目前版本的 Rich Menu，再確認套用",
                    code="rich_menu_preview_stale",
                )
        return {
            "preview_id": preview_id,
            "config_revision": revision,
            "config_fingerprint": fingerprint,
        }
    finally:
        conn.close()


def create_publication_job(
    menu_id: str,
    requested_by_admin_user_id: int | None,
    *,
    preview_id: int,
) -> dict[str, Any]:
    if requested_by_admin_user_id is None:
        raise RichMenuPublicationConflictError(
            "發布需要已登入的管理員",
            code="authenticated_admin_required",
        )
    menu, revision, fingerprint = _current_menu_snapshot(menu_id)

    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT id FROM line_rich_menu_publish_previews
                WHERE id=%s AND menu_config_id=%s AND config_revision=%s
                  AND config_fingerprint=%s AND previewed_by_admin_user_id=%s
                  AND publication_id IS NULL
                FOR UPDATE
                """,
                (preview_id, menu_id, revision, fingerprint, requested_by_admin_user_id),
            )
            if not cursor.fetchone():
                raise RichMenuPublicationConflictError(
                    "請先預覽目前版本的 Rich Menu，再確認套用",
                    code="rich_menu_preview_stale",
                )
            cursor.execute(
                """
                SELECT id FROM line_rich_menu_publications
                WHERE menu_config_id=%s AND status IN ('pending','processing')
                LIMIT 1 FOR UPDATE
                """,
                (menu_id,),
            )
            active = cursor.fetchone()
            if active:
                raise RichMenuPublicationConflictError(
                    f"此選單已有發布工作 #{active['id']} 正在處理"
                )
            cursor.execute(
                """
                INSERT INTO line_rich_menu_publications (
                    menu_config_id, audience_role, config_revision, config_snapshot,
                    image_asset_id, requested_by_admin_user_id
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    menu.id,
                    menu.audience_role,
                    revision,
                    json.dumps(menu.model_dump(mode="json"), ensure_ascii=False),
                    menu.appearance.image_asset_id,
                    requested_by_admin_user_id,
                ),
            )
            publication_id = int(cursor.lastrowid)
            cursor.execute(
                """
                UPDATE line_rich_menu_publish_previews
                SET publication_id=%s, confirmed_at=UTC_TIMESTAMP()
                WHERE id=%s
                """,
                (publication_id, preview_id),
            )
        conn.commit()
        return get_publication(publication_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_publication(publication_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM line_rich_menu_publications WHERE id=%s",
                (publication_id,),
            )
            item = cursor.fetchone()
        if not item:
            raise RichMenuPublicationNotFoundError(
                f"找不到 Rich Menu 發布工作 #{publication_id}"
            )
        item["config_snapshot"] = _decode_json(item.get("config_snapshot"))
        return item
    finally:
        conn.close()


def list_publications(
    *,
    menu_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    allowed_statuses = {"pending", "processing", "published", "failed"}
    if status and status not in allowed_statuses:
        raise ValueError("不支援的發布狀態")
    clauses = ["1=1"]
    params: list[Any] = []
    if menu_id:
        clauses.append("menu_config_id=%s")
        params.append(menu_id)
    if status:
        clauses.append("status=%s")
        params.append(status)
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size
    where_sql = " AND ".join(clauses)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(1) AS total FROM line_rich_menu_publications WHERE {where_sql}",
                params,
            )
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                f"""
                SELECT id, menu_config_id, audience_role, config_revision, status,
                       line_rich_menu_id, previous_line_rich_menu_id, image_asset_id,
                       retry_count, max_retries, is_current, error_code, error_message,
                       created_at, started_at, published_at, failed_at, updated_at
                FROM line_rich_menu_publications
                WHERE {where_sql}
                ORDER BY id DESC LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            items = list(cursor.fetchall())
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    finally:
        conn.close()


def retry_publication(publication_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id,status FROM line_rich_menu_publications WHERE id=%s FOR UPDATE",
                (publication_id,),
            )
            item = cursor.fetchone()
            if not item:
                raise RichMenuPublicationNotFoundError(
                    f"找不到 Rich Menu 發布工作 #{publication_id}"
                )
            if item["status"] != "failed":
                raise RichMenuPublicationConflictError("只有失敗的發布工作可以重試")
            cursor.execute(
                """
                UPDATE line_rich_menu_publications
                SET status='pending', retry_count=0, next_retry_at=NULL,
                    processing_started_at=NULL, error_code=NULL, error_message=NULL,
                    failed_at=NULL
                WHERE id=%s
                """,
                (publication_id,),
            )
        conn.commit()
        return get_publication(publication_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_current_rich_menu_id(audience_role: str) -> str:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT line_rich_menu_id FROM line_rich_menu_publications
                WHERE audience_role=%s AND status='published' AND is_current=TRUE
                ORDER BY published_at DESC, id DESC LIMIT 1
                """,
                (audience_role,),
            )
            row = cursor.fetchone()
        if not row:
            return ""
        return str(row.get("line_rich_menu_id") if isinstance(row, dict) else row[0] or "")
    except pymysql.MySQLError:
        return ""
    finally:
        conn.close()


def import_legacy_rich_menu_ids() -> int:
    """Register existing JSON IDs once without republishing or contacting LINE."""
    try:
        legacy = json.loads(LEGACY_IDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    config, revision = _current_menu_configuration()
    key_by_role = {
        "customer": "default_rich_menu_id",
        "staff": "staff_rich_menu_id",
        "union_staff": "union_staff_rich_menu_id",
    }
    imported = 0
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            for menu in config.menus:
                rich_menu_id = str(legacy.get(key_by_role[menu.audience_role]) or "").strip()
                if not rich_menu_id:
                    continue
                cursor.execute(
                    """
                    SELECT id FROM line_rich_menu_publications
                    WHERE audience_role=%s AND is_current=TRUE LIMIT 1 FOR UPDATE
                    """,
                    (menu.audience_role,),
                )
                if cursor.fetchone():
                    continue
                cursor.execute(
                    """
                    INSERT INTO line_rich_menu_publications (
                        menu_config_id, audience_role, config_revision, config_snapshot,
                        status, line_rich_menu_id, is_current, published_at
                    ) VALUES (%s,%s,%s,%s,'published',%s,TRUE,UTC_TIMESTAMP())
                    """,
                    (
                        menu.id,
                        menu.audience_role,
                        revision,
                        json.dumps(menu.model_dump(mode="json"), ensure_ascii=False),
                        rich_menu_id,
                    ),
                )
                imported += 1
        conn.commit()
        return imported
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def recover_stale_publications() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE line_rich_menu_publications
                SET status='pending', processing_started_at=NULL,
                    error_code='stale_recovered'
                WHERE status='processing'
                  AND processing_started_at < UTC_TIMESTAMP() - INTERVAL 10 MINUTE
                """
            )
        conn.commit()
    finally:
        conn.close()


def next_publication_run_at() -> datetime | None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MIN(COALESCE(next_retry_at,created_at))
                FROM line_rich_menu_publications WHERE status='pending'
                """
            )
            row = cursor.fetchone()
        return next(iter(row.values()), None) if isinstance(row, dict) else row[0] if row else None
    finally:
        conn.close()


def _claim_publications(limit: int = 2) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT * FROM line_rich_menu_publications
                WHERE status='pending'
                  AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP())
                ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            items = list(cursor.fetchall())
            for item in items:
                cursor.execute(
                    """
                    UPDATE line_rich_menu_publications
                    SET status='processing', processing_started_at=UTC_TIMESTAMP(),
                        started_at=COALESCE(started_at,UTC_TIMESTAMP())
                    WHERE id=%s
                    """,
                    (item["id"],),
                )
        conn.commit()
        for item in items:
            item["config_snapshot"] = _decode_json(item["config_snapshot"])
        return items
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_line_action(action: dict[str, Any]) -> dict[str, str]:
    if action["type"] == "message":
        return {"type": "message", "text": action["text"]}
    if action["type"] == "postback":
        return {"type": "postback", "data": action["data"]}
    if action.get("uri_source") == "liff":
        liff_id = os.getenv("LINE_LIFF_ID", "").strip()
        if not liff_id:
            raise RichMenuPublishError(
                "liff_not_configured",
                "LINE_LIFF_ID 尚未設定",
                retryable=False,
            )
        suffix = (action.get("uri") or "").strip()
        uri = f"https://liff.line.me/{liff_id}"
        if suffix.startswith(("?", "#")):
            uri += suffix
        return {"type": "uri", "uri": uri}
    return {"type": "uri", "uri": action["uri"]}


def build_line_menu(menu: dict[str, Any]) -> dict[str, Any]:
    validated = RichMenuDefinition.model_validate(menu)
    data = validated.model_dump(mode="json")
    return {
        "size": data["size"],
        "selected": data.get("selected", True),
        "name": data["name"],
        "chatBarText": data["chat_bar_text"],
        "areas": [
            {"bounds": item["bounds"], "action": build_line_action(item["action"])}
            for item in data["buttons"]
        ],
    }


def _line_request(method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
    except requests.RequestException as exc:
        raise RichMenuPublishError("network_error", str(exc), retryable=True) from exc
    if not response.ok:
        raise RichMenuPublishError(
            f"http_{response.status_code}",
            response.text[:4000],
            retryable=response.status_code in RETRYABLE_HTTP,
        )
    return response


def _publish_to_line(item: dict[str, Any]) -> tuple[str, int]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token or token == "mock_token" or token.startswith("your_"):
        raise RichMenuPublishError(
            "line_token_not_configured",
            "LINE_CHANNEL_ACCESS_TOKEN 尚未設定",
            retryable=False,
        )
    menu = item["config_snapshot"]
    appearance = menu.get("appearance", {})
    if appearance.get("image_mode", "generated") == "generated":
        if item.get("image_asset_id"):
            asset = get_media_asset(int(item["image_asset_id"]))
        else:
            asset = store_generated_rich_menu_image(
                menu,
                created_by_admin_user_id=item.get("requested_by_admin_user_id"),
            )
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE line_rich_menu_publications SET image_asset_id=%s WHERE id=%s",
                        (asset["id"], item["id"]),
                    )
                conn.commit()
            finally:
                conn.close()
            item["image_asset_id"] = asset["id"]
    else:
        asset = get_media_asset(int(appearance["image_asset_id"]))
    _, image_content = read_media_asset(int(asset["id"]))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    created_id = ""
    try:
        created = _line_request(
            "POST",
            "https://api.line.me/v2/bot/richmenu",
            headers=headers,
            json=build_line_menu(menu),
        )
        created_id = created.json()["richMenuId"]
        _line_request(
            "POST",
            f"https://api-data.line.me/v2/bot/richmenu/{created_id}/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
            data=image_content,
        )
        if menu.get("set_as_default"):
            _line_request(
                "POST",
                f"https://api.line.me/v2/bot/user/all/richmenu/{created_id}",
                headers=headers,
            )
        return created_id, int(asset["id"])
    except Exception:
        if created_id:
            try:
                requests.delete(
                    f"https://api.line.me/v2/bot/richmenu/{created_id}",
                    headers=headers,
                    timeout=10,
                )
            except requests.RequestException:
                pass
        raise


def _write_legacy_id(audience_role: str, rich_menu_id: str) -> None:
    key = {
        "customer": "default_rich_menu_id",
        "staff": "staff_rich_menu_id",
        "union_staff": "union_staff_rich_menu_id",
    }[audience_role]
    try:
        existing = json.loads(LEGACY_IDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = {}
    existing[key] = rich_menu_id
    LEGACY_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".rich-menu-ids-", suffix=".tmp", dir=LEGACY_IDS_PATH.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(existing, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, LEGACY_IDS_PATH)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _complete_publication(item: dict[str, Any], rich_menu_id: str, asset_id: int) -> None:
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT line_rich_menu_id FROM line_rich_menu_publications
                WHERE menu_config_id=%s AND is_current=TRUE
                ORDER BY id DESC LIMIT 1 FOR UPDATE
                """,
                (item["menu_config_id"],),
            )
            previous = cursor.fetchone()
            previous_id = previous["line_rich_menu_id"] if previous else None
            cursor.execute(
                "UPDATE line_rich_menu_publications SET is_current=FALSE WHERE menu_config_id=%s",
                (item["menu_config_id"],),
            )
            cursor.execute(
                """
                UPDATE line_rich_menu_publications
                SET status='published', line_rich_menu_id=%s,
                    previous_line_rich_menu_id=%s, image_asset_id=%s,
                    is_current=TRUE, published_at=UTC_TIMESTAMP(),
                    processing_started_at=NULL, next_retry_at=NULL,
                    error_code=NULL, error_message=NULL
                WHERE id=%s
                """,
                (rich_menu_id, previous_id, asset_id, item["id"]),
            )
            if item["audience_role"] in {"staff", "union_staff"}:
                cursor.execute(
                    """
                    SELECT line_user_id FROM line_users
                    WHERE role=%s AND status='active'
                    """,
                    (item["audience_role"],),
                )
                for user in cursor.fetchall():
                    user_id = user["line_user_id"]
                    enqueue_line_task(
                        cursor,
                        to_user_id=user_id,
                        task_type="rich_menu_link",
                        payload={"rich_menu_id": rich_menu_id},
                        idempotency_key=f"rich-menu-publication:{item['id']}:{user_id}",
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    try:
        _write_legacy_id(item["audience_role"], rich_menu_id)
    except OSError as exc:
        # MySQL is the authoritative runtime state; the JSON file is only a
        # temporary compatibility bridge for older code and deployments.
        print(f"[Rich Menu] Failed to update legacy id file: {exc}")


def _fail_publication(item: dict[str, Any], exc: Exception) -> None:
    retryable = isinstance(exc, RichMenuPublishError) and exc.retryable
    code = exc.code if isinstance(exc, RichMenuPublishError) else "publish_exception"
    retry_count = int(item.get("retry_count") or 0) + 1
    will_retry = retryable and retry_count <= int(item.get("max_retries") or 0)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if will_retry:
                delay = min(60 * (2 ** (retry_count - 1)), 3600)
                cursor.execute(
                    """
                    UPDATE line_rich_menu_publications
                    SET status='pending', retry_count=%s,
                        next_retry_at=DATE_ADD(UTC_TIMESTAMP(),INTERVAL %s SECOND),
                        processing_started_at=NULL, error_code=%s, error_message=%s
                    WHERE id=%s
                    """,
                    (retry_count, delay, code, str(exc)[:4000], item["id"]),
                )
            else:
                cursor.execute(
                    """
                    UPDATE line_rich_menu_publications
                    SET status='failed', retry_count=%s, failed_at=UTC_TIMESTAMP(),
                        processing_started_at=NULL, next_retry_at=NULL,
                        error_code=%s, error_message=%s
                    WHERE id=%s
                    """,
                    (retry_count, code, str(exc)[:4000], item["id"]),
                )
        conn.commit()
    finally:
        conn.close()


def process_due_publications() -> int:
    processed = 0
    while True:
        items = _claim_publications()
        if not items:
            return processed
        for item in items:
            try:
                rich_menu_id, asset_id = _publish_to_line(item)
                _complete_publication(item, rich_menu_id, asset_id)
            except Exception as exc:
                _fail_publication(item, exc)
            processed += 1
