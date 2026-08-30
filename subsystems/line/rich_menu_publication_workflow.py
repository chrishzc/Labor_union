"""
File: rich_menu_publication_workflow.py
Description: 建立零寫入預覽收據並維持既有 Rich Menu 發布相容流程。
"""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pymysql

from domains.line.canonical_payload import canonical_line_payload_json
from subsystems.line.rich_menu_models import LineMenusConfig, RichMenuDefinition
from domains.line.configuration import LineConfigurationKind
from domains.line.identities import LineRichMenuPublicationId
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyReceipt
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import unconfigured_connection_factory
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.message_configuration import configuration_definition
from subsystems.line.ports import LineAuditIntent, LineRichMenuPublicationPage
from subsystems.line.rich_menu_binding import schedule_published_menu_rebindings
from subsystems.line.rich_menu_contracts import (
    LineRichMenuPublicationQuery,
    LineRichMenuProviderRequest,
    QueueLineRichMenuPublicationCommand,
)
from subsystems.line.rich_menu_definition import rich_menu_provider_definition
from subsystems.line.media_archive import (
    MediaValidationError,
    get_media_asset,
    read_media_asset,
    store_generated_rich_menu_image,
)


get_connection = unconfigured_connection_factory


def _unconfigured_unit_of_work() -> Any:
    raise RuntimeError("LINE unit-of-work factory is not configured")


open_line_unit_of_work = _unconfigured_unit_of_work
line_unit_of_work_factory = None


class _ConnectionUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __enter__(self):
        begin = getattr(self._connection, "begin", None)
        if callable(begin):
            begin()
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self._connection.rollback()
        return False

    def commit(self) -> None:
        self._connection.commit()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_IDS_PATH = PROJECT_ROOT / "config" / "rich_menu_ids.json"
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


def create_publication_preview(
    menu_id: str,
    previewed_by_admin_user_id: int | None,
    *,
    config_revision: int,
    candidate: Mapping[str, object],
) -> dict[str, Any]:
    if (
        not isinstance(previewed_by_admin_user_id, int)
        or isinstance(previewed_by_admin_user_id, bool)
        or previewed_by_admin_user_id <= 0
    ):
        raise RichMenuPublicationConflictError(
            "發布預覽需要已登入的管理員",
            code="authenticated_admin_required",
        )
    if not isinstance(menu_id, str) or menu_id.strip() != menu_id or not menu_id:
        raise ValueError("LINE Rich Menu preview menu ID is invalid")
    if len(menu_id) > 191:
        raise ValueError("LINE Rich Menu preview menu ID is too long")
    if (
        not isinstance(config_revision, int)
        or isinstance(config_revision, bool)
        or config_revision < 0
    ):
        raise ValueError("LINE Rich Menu preview revision is invalid")
    if not isinstance(candidate, Mapping):
        raise TypeError("LINE Rich Menu preview candidate must be a mapping")
    fingerprint = _candidate_fingerprint(candidate)
    preview_id = _preview_id(
        previewed_by_admin_user_id,
        menu_id,
        config_revision,
        fingerprint,
    )
    return {
        "preview_id": preview_id,
        "config_revision": str(config_revision),
        "config_fingerprint": fingerprint,
    }


def validate_publication_preview(
    menu_id: str,
    preview_id: int,
    previewed_by_admin_user_id: int | None,
) -> dict[str, Any]:
    if (
        not isinstance(previewed_by_admin_user_id, int)
        or isinstance(previewed_by_admin_user_id, bool)
        or previewed_by_admin_user_id <= 0
    ):
        raise RichMenuPublicationConflictError(
            "發布需要已登入的管理員",
            code="authenticated_admin_required",
        )
    if not isinstance(preview_id, int) or isinstance(preview_id, bool) or preview_id <= 0:
        raise ValueError("LINE Rich Menu preview ID is invalid")
    menu, revision, candidate = _current_publication_candidate(menu_id)
    revision_number = int(revision)
    fingerprint = _candidate_fingerprint(candidate)
    expected_preview_id = _preview_id(
        previewed_by_admin_user_id,
        menu.id,
        revision_number,
        fingerprint,
    )
    if preview_id != expected_preview_id:
        raise RichMenuPublicationConflictError(
            "請先預覽目前版本的 Rich Menu，再確認套用",
            code="rich_menu_preview_stale",
        )
    return {
        "preview_id": preview_id,
        "config_revision": str(revision_number),
        "config_fingerprint": fingerprint,
    }


def queue_publication(
    command: QueueLineRichMenuPublicationCommand,
    *,
    reason: str,
):
    """在單一 LINE UoW 內建立 publication、receipt、audit 與首次 outbox。"""

    require_line_capability(command.actor, LineCapability.MENU_PUBLISH)
    if not isinstance(reason, str) or reason.strip() != reason or not reason:
        raise ValueError("LINE Rich Menu publication reason is invalid")
    if len(reason) > 500:
        raise ValueError("LINE Rich Menu publication reason is too long")
    with open_line_unit_of_work() as unit_of_work:
        menu = _locked_menu(unit_of_work, command)
        fresh_candidate = {
            "menu_definition": menu,
            "provider_definition": json.loads(rich_menu_provider_definition(menu)),
        }
        fresh_fingerprint = _candidate_fingerprint(fresh_candidate)
        if command.preview_config_revision != str(command.configuration_revision.value):
            raise RichMenuPublicationConflictError(
                "Rich Menu 預覽版本已過期",
                code="rich_menu_preview_stale",
            )
        if command.preview_config_fingerprint != fresh_fingerprint:
            raise RichMenuPublicationConflictError(
                "Rich Menu 預覽內容已變更",
                code="rich_menu_preview_stale",
            )
        if command.preview_id != _preview_id(
            command.previewed_by_admin_user_id,
            command.menu_definition_id,
            command.configuration_revision.value,
            fresh_fingerprint,
        ):
            raise RichMenuPublicationConflictError(
                "Rich Menu 預覽收據已過期",
                code="rich_menu_preview_stale",
            )
        command_fingerprint = fingerprint_payload(
            {
                "menu_definition_id": command.menu_definition_id,
                "configuration_revision": command.configuration_revision.value,
                "preview_id": command.preview_id,
                "preview_config_revision": command.preview_config_revision,
                "preview_config_fingerprint": command.preview_config_fingerprint,
                "reason": reason,
                "menu": menu,
            }
        )
        existing = unit_of_work.receipts.get(command.idempotency_key)
        if existing is not None:
            if existing.payload_fingerprint != command_fingerprint:
                raise RichMenuPublicationConflictError(
                    "相同套用鍵對應不同 Rich Menu 請求",
                    code="line_rich_menu_command_idempotency_conflict",
                )
            try:
                publication_id = int(existing.result_reference.rsplit(":", 1)[-1])
            except (AttributeError, ValueError) as error:
                raise RuntimeError("line_rich_menu_receipt_reference_invalid") from error
            result = unit_of_work.rich_menu_publications.get(
                LineRichMenuPublicationId(publication_id)
            )
            if result is None:
                raise RuntimeError("line_rich_menu_receipt_result_missing")
            return result

        queued = unit_of_work.rich_menu_publications.queue(command)
        publication = queued.publication
        result_reference = f"line-rich-menu-publication:{publication.publication_id.value}"
        unit_of_work.receipts.append(
            IdempotencyReceipt(command.idempotency_key, command_fingerprint, result_reference)
        )
        unit_of_work.audit.append(
            LineAuditIntent(
                "line.rich_menu.queue",
                command.actor.actor_id,
                "line_rich_menu_publication",
                str(publication.publication_id.value),
            )
        )
        unit_of_work.outbox.append(
            OutboxIntent(
                "line_rich_menu_publication",
                str(publication.publication_id.value),
                "line.rich_menu.publish",
                json.dumps(
                    {
                        "configuration_revision": command.configuration_revision.value,
                        "correlation_id": command.correlation_id.value,
                        "menu_definition_id": command.menu_definition_id,
                        "preview_fingerprint": command.preview_config_fingerprint,
                        "publication_id": publication.publication_id.value,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                result_reference,
            )
        )
        unit_of_work.commit()
    return publication


def list_publication_page(
    query: LineRichMenuPublicationQuery,
    *,
    offset: int,
    actor,
) -> LineRichMenuPublicationPage:
    """直接委派 repository 的 COUNT/LIMIT/OFFSET，不建立記憶體假分頁。"""

    require_line_capability(actor, LineCapability.CONFIG_READ)
    with open_line_unit_of_work() as unit_of_work:
        return unit_of_work.rich_menu_publications.list_page(query, offset=offset)


def get_publication_step_receipts(
    publication_id: LineRichMenuPublicationId,
    actor,
):
    """讀取已確認步驟；只回傳 typed port 結果，不開啟任何寫入。"""

    require_line_capability(actor, LineCapability.CONFIG_READ)
    with open_line_unit_of_work() as unit_of_work:
        return unit_of_work.rich_menu_publications.list_step_receipts(publication_id)


def _current_publication_candidate(
    menu_id: str,
) -> tuple[RichMenuDefinition, str, dict[str, object]]:
    with open_line_unit_of_work() as unit_of_work:
        configuration_snapshot = unit_of_work.configurations.get(
            LineConfigurationKind.RICH_MENUS
        )
    definition = configuration_definition(configuration_snapshot)
    menu = next(
        (
            item
            for item in definition.get("menus", [])
            if isinstance(item, dict) and item.get("id") == menu_id
        ),
        None,
    )
    if menu is None:
        raise RichMenuPublicationNotFoundError(f"找不到 Rich Menu {menu_id}")
    validated = RichMenuDefinition.model_validate(menu)
    if not validated.enabled:
        raise RichMenuPublicationConflictError("停用中的 Rich Menu 不能發布")
    if validated.appearance.image_mode == "uploaded":
        if not validated.appearance.image_asset_id:
            raise RichMenuPublicationConflictError("上傳圖片模式尚未選擇圖片資產")
        asset = get_media_asset(validated.appearance.image_asset_id)
        if (asset.get("width"), asset.get("height")) != (
            validated.size.width,
            validated.size.height,
        ):
            raise RichMenuPublicationConflictError("圖片尺寸與 Rich Menu 尺寸不一致")
    candidate = {
        "menu_definition": menu,
        "provider_definition": json.loads(rich_menu_provider_definition(menu)),
    }
    return validated, str(configuration_snapshot.revision.value), candidate


def _candidate_fingerprint(candidate: Mapping[str, object]) -> str:
    candidate_json = json.dumps(
        dict(candidate),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(candidate_json.encode("utf-8")).hexdigest()


def _preview_id(actor_id: int, menu_id: str, config_revision: int, fingerprint: str) -> int:
    receipt_json = json.dumps(
        {
            "actor_id": actor_id,
            "menu_definition_id": menu_id,
            "configuration_revision": config_revision,
            "candidate_fingerprint": fingerprint,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    receipt_digest = hashlib.sha256(receipt_json.encode("utf-8")).digest()
    preview_id = int.from_bytes(receipt_digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF
    return preview_id or 1


def _locked_menu(unit_of_work, command: QueueLineRichMenuPublicationCommand):
    snapshot = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
    if snapshot.revision != command.configuration_revision:
        raise RichMenuPublicationConflictError(
            "Rich Menu 設定已變更，請重新預覽",
            code="line_rich_menu_configuration_revision_conflict",
        )
    definition = configuration_definition(snapshot)
    menu = next(
        (
            item
            for item in definition.get("menus", [])
            if isinstance(item, dict) and item.get("id") == command.menu_definition_id
        ),
        None,
    )
    if menu is None or menu.get("enabled", True) is not True:
        raise RichMenuPublicationNotFoundError("找不到可發布的 Rich Menu")
    validated = RichMenuDefinition.model_validate(menu)
    if validated.appearance.image_mode == "uploaded":
        if not validated.appearance.image_asset_id:
            raise RichMenuPublicationConflictError("上傳圖片模式尚未選擇圖片資產")
        asset = get_media_asset(validated.appearance.image_asset_id)
        if (asset.get("width"), asset.get("height")) != (
            validated.size.width,
            validated.size.height,
        ):
            raise RichMenuPublicationConflictError("圖片尺寸與 Rich Menu 尺寸不一致")
    rich_menu_provider_definition(menu)
    return menu


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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
        return get_publication(publication_id)
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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
        return get_publication(publication_id)
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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
        return imported
    finally:
        conn.close()


def recover_stale_publications() -> None:
    conn = get_connection()
    try:
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
        for item in items:
            item["config_snapshot"] = _decode_json(item["config_snapshot"])
        return items
    finally:
        conn.close()


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
            item["image_asset_id"] = asset["id"]
    else:
        asset = get_media_asset(int(appearance["image_asset_id"]))
    _, image_content = read_media_asset(int(asset["id"]))
    image_type = str(asset.get("mime_type") or "image/jpeg")
    provider = LineRichMenuApiAdapter(
        token,
        lambda _reference: (image_content, image_type),
    )
    outcome = provider.publish(
        LineRichMenuProviderRequest(
            LineRichMenuPublicationId(int(item["id"])),
            canonical_line_payload_json(menu),
            f"line-media-asset:{int(asset['id'])}",
        )
    )
    if outcome.outcome_type.value != "success":
        retryable = outcome.outcome_type.value in {
            "rate_limited",
            "unavailable",
            "timeout",
        }
        raise RichMenuPublishError(
            outcome.error_code or "line_rich_menu_provider_failure",
            outcome.error_message or "LINE Rich Menu provider request failed",
            retryable=retryable,
        )
    if not outcome.provider_menu_id:
        raise RichMenuPublishError(
            "line_rich_menu_provider_id_missing",
            "LINE Rich Menu provider success acknowledgement was incomplete",
            retryable=True,
        )
    return outcome.provider_menu_id, int(asset["id"])


def _write_legacy_id(audience_role: str, rich_menu_id: str) -> None:
    key = {
        "customer": "default_rich_menu_id",
        "staff": "staff_rich_menu_id",
        "union_staff": "union_staff_rich_menu_id",
    }.get(audience_role)
    if key is None:
        return
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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
                if item["audience_role"] in {"customer", "staff", "union_staff"}:
                    if not all(
                        getattr(unit_of_work, name, None) is not None
                        for name in ("identities", "outbox")
                    ):
                        raise RuntimeError(
                            "canonical LINE unit-of-work is required for Rich Menu rebindings"
                        )
                    schedule_published_menu_rebindings(
                        unit_of_work,
                        canonical_line_payload_json(item["config_snapshot"]),
                        LineRichMenuPublicationId(int(item["id"])),
                        rich_menu_id,
                    )
            unit_of_work.commit()
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
        with (line_unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
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
            unit_of_work.commit()
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
