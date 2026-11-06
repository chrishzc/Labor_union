"""Validated media storage; database stores metadata while files stay outside Git."""

from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

import pymysql
from PIL import Image, UnidentifiedImageError

from subsystems.line.ports import unconfigured_connection_factory
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.controlled_files.workflow import StageControlledFile, ControlledFileOwner, ControlledFilePurpose, ControlledFileIntent, ApplyControlledFile, ControlledFileWorkflowError


class RichMenuImageRenderer(Protocol):
    def __call__(self, menu: dict[str, object]) -> bytes: ...


class ImageEncoder(Protocol):
    def __call__(self, image: Image.Image) -> bytes: ...


def _unconfigured_renderer(_: dict[str, object]) -> bytes:
    raise RuntimeError("LINE Rich Menu image renderer is not configured")


def _unconfigured_encoder(_: Image.Image) -> bytes:
    raise RuntimeError("LINE Rich Menu image encoder is not configured")


get_connection = unconfigured_connection_factory
render_rich_menu_image: RichMenuImageRenderer = _unconfigured_renderer
encode_line_jpeg: ImageEncoder = _unconfigured_encoder
encode_line_png: ImageEncoder = _unconfigured_encoder


def _unconfigured_controlled_files(connection):
    raise RuntimeError("LINE controlled-file workflow is not configured")


controlled_file_workflow_factory = _unconfigured_controlled_files
media_asset_writer_factory = _unconfigured_controlled_files
def _unconfigured_storage_provider():
    raise RuntimeError("LINE controlled-file storage provider is not configured")


media_asset_storage_provider = _unconfigured_storage_provider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class MediaValidationError(ValueError):
    pass


class MediaAssetNotFoundError(LookupError):
    pass


def _unconfigured_storage_root() -> Path:
    raise RuntimeError("LINE media storage root is not configured")


def _unconfigured_storage_write() -> None:
    raise RuntimeError("LINE media storage writer is not configured")


storage_root_provider: Callable[[], Path] = _unconfigured_storage_root
prepare_storage_write: Callable[[], None] = _unconfigured_storage_write


def media_storage_root() -> Path:
    return storage_root_provider()


def normalize_uploaded_rich_menu_image(
    content: bytes,
    *,
    expected_width: int,
    expected_height: int,
) -> bytes:
    if not content:
        raise MediaValidationError("圖片內容不可為空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise MediaValidationError("上傳圖片超過系統允許大小")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            if source.format not in {"JPEG", "PNG"}:
                raise MediaValidationError("只接受 JPEG 或 PNG 圖片")
            if source.size != (expected_width, expected_height):
                raise MediaValidationError(
                    f"圖片尺寸必須是 {expected_width}x{expected_height}"
                )
            return encode_line_png(source)
    except UnidentifiedImageError as exc:
        raise MediaValidationError("檔案不是有效圖片") from exc


def _safe_storage_path(storage_key: str) -> Path:
    root = media_storage_root()
    target = (root / storage_key).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MediaValidationError("媒體路徑超出受控儲存區") from exc
    return target


def _save_asset(
    content: bytes,
    *,
    menu_id: str,
    original_filename: str,
    width: int,
    height: int,
    created_by_admin_user_id: int | None,
    generated: bool,
    connection_factory: Callable[[], Any] | None = None,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256(content).hexdigest()
    filename = f"generated-{menu_id}.png" if generated else str(Path(original_filename).with_suffix(".png").name)
    identity = hashlib.sha256((menu_id + ":" + filename + ":" + digest).encode()).hexdigest()
    operation_id = identity if generated else identity + ":" + uuid.uuid4().hex
    actor = ActorContext(f"admin:{created_by_admin_user_id}" if created_by_admin_user_id is not None else "system:line-rich-menu")
    correlation = CorrelationId("line-rich-menu-media:" + identity[:32])
    conn = (connection_factory or get_connection)()
    try:
        controlled_files = controlled_file_workflow_factory(conn)
        metadata = media_asset_writer_factory(conn)
        if generated:
            existing = metadata.find_generated_asset(identity, menu_id)
            if existing is not None:
                _require_generated_replay(existing, controlled_files, menu_id, digest, len(content))
                return existing
        staged = controlled_files.stage(StageControlledFile(
            ControlledFileOwner.LINE_INTEGRATION, ControlledFilePurpose.RICH_MENU_BACKGROUND,
            menu_id, "asset:" + identity, "line/rich-menus/" + menu_id, filename, "image/png", content,
            IdempotencyKey("line-menu-media:" + operation_id + ":stage"), actor, correlation))
        intent = ControlledFileIntent(staged.staging_id, ControlledFileOwner.LINE_INTEGRATION,
            ControlledFilePurpose.RICH_MENU_BACKGROUND, menu_id, "asset:" + identity, "line/rich-menus/" + menu_id)
        with (unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
            try:
                preview = controlled_files.preview(intent)
            except ControlledFileWorkflowError as error:
                # A concurrent identical generated materialization may have
                # committed its object and media FK since our first read.
                if not generated or getattr(error, "code", None) != "controlled_file_already_registered":
                    raise
                existing = metadata.find_generated_asset(identity, menu_id, for_update=True)
                if existing is None:
                    raise
                _require_generated_replay(existing, controlled_files, menu_id, digest, len(content))
                unit_of_work.commit()
                return existing
            receipt = controlled_files.apply_borrowed(ApplyControlledFile(intent, preview.expected_staging_version,
                preview.preview_fingerprint, IdempotencyKey("line-menu-media:" + operation_id + ":apply"), actor, correlation))
            asset = metadata.register_controlled_asset(receipt.readback, menu_id=menu_id,
                width=width, height=height, created_by_admin_user_id=created_by_admin_user_id,
                storage_provider=media_asset_storage_provider())
            unit_of_work.commit()
    finally:
        conn.close()
    return asset


def _require_generated_replay(asset, controlled_files, menu_id, digest, size_bytes):
    file_id = asset.get("controlled_file_id")
    if (asset.get("controlled_file_object_id") is None or not file_id or asset["storage_key"] != file_id
        or asset.get("category") != "rich_menu" or asset.get("owner_type") != "line_menu"
        or asset["owner_id"] != menu_id or asset["sha256"] != digest or asset["file_size"] != size_bytes
        or asset["mime_type"] != "image/png" or asset.get("deleted_at") is not None):
        raise MediaValidationError("既有選單圖片識別或內容不一致")
    reference = controlled_files.readback(file_id)
    if (reference.owner is not ControlledFileOwner.LINE_INTEGRATION
        or reference.purpose is not ControlledFilePurpose.RICH_MENU_BACKGROUND
        or reference.subject_reference != menu_id or reference.sha256_digest != digest
        or reference.size_bytes != size_bytes or reference.mime_type != "image/png"):
        raise MediaValidationError("既有選單正式檔案事實不一致")
    observed = controlled_files.download(file_id)
    if hashlib.sha256(observed.content).hexdigest() != digest:
        raise MediaValidationError("既有選單圖片內容完整性驗證失敗")


def store_uploaded_rich_menu_image(
    content: bytes,
    *,
    menu_id: str,
    original_filename: str,
    expected_width: int,
    expected_height: int,
    created_by_admin_user_id: int | None,
    connection_factory: Callable[[], Any] | None = None,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_uploaded_rich_menu_image(
        content,
        expected_width=expected_width,
        expected_height=expected_height,
    )
    return _save_asset(
        normalized,
        menu_id=menu_id,
        original_filename=Path(original_filename).name,
        width=expected_width,
        height=expected_height,
        created_by_admin_user_id=created_by_admin_user_id,
        generated=False,
        connection_factory=connection_factory,
        unit_of_work_factory=unit_of_work_factory,
    )


def store_generated_rich_menu_image(
    menu: dict[str, Any],
    *,
    created_by_admin_user_id: int | None,
    connection_factory: Callable[[], Any] | None = None,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    content = render_rich_menu_image(menu)
    return _save_asset(
        content,
        menu_id=menu["id"],
        original_filename=f"generated-{menu['id']}.jpg",
        width=int(menu["size"]["width"]),
        height=int(menu["size"]["height"]),
        created_by_admin_user_id=created_by_admin_user_id,
        generated=True,
        connection_factory=connection_factory,
        unit_of_work_factory=unit_of_work_factory,
    )


def get_media_asset(asset_id: int, *, connection_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    conn = (connection_factory or get_connection)()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT asset.*,object.opaque_object_id controlled_file_id FROM media_assets asset "
                "LEFT JOIN controlled_file_objects object ON object.id=asset.controlled_file_object_id "
                "WHERE asset.id=%s AND asset.deleted_at IS NULL",
                (asset_id,),
            )
            asset = cursor.fetchone()
        if not asset:
            raise MediaAssetNotFoundError(f"找不到媒體資產 #{asset_id}")
        return asset
    finally:
        conn.close()


def read_media_asset(asset_id: int, *, connection_factory: Callable[[], Any] | None = None) -> tuple[dict[str, Any], bytes]:
    asset = get_media_asset(asset_id, connection_factory=connection_factory)
    if asset.get("controlled_file_object_id") is not None:
        if asset.get("controlled_file_id") != asset["storage_key"]:
            raise MediaValidationError("媒體資產正式檔案識別不一致")
        content, mime_type = read_controlled_media(asset["storage_key"], connection_factory=connection_factory)
        if (mime_type != asset["mime_type"] or len(content) != asset["file_size"]
            or hashlib.sha256(content).hexdigest() != asset["sha256"]):
            raise MediaValidationError("媒體資產與正式檔案版本不一致")
        return asset, content
    path = _safe_storage_path(asset["storage_key"])
    if not path.is_file():
        raise MediaAssetNotFoundError(f"媒體資產 #{asset_id} 的檔案不存在")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != asset["sha256"]:
        raise MediaValidationError(f"媒體資產 #{asset_id} 完整性驗證失敗")
    return asset, content


def read_controlled_media(file_id: str, *, connection_factory=None) -> tuple[bytes, str]:
    conn = (connection_factory or get_connection)()
    try:
        workflow = controlled_file_workflow_factory(conn)
        readback = workflow.readback(file_id)
        if (readback.owner is not ControlledFileOwner.LINE_INTEGRATION
            or readback.purpose is not ControlledFilePurpose.RICH_MENU_BACKGROUND):
            raise MediaValidationError("檔案不是 LINE 選單底圖")
        content = workflow.download(file_id)
        return content.content, content.content_type
    finally:
        conn.close()


def delete_media_asset(
    asset_id: int,
    *,
    connection_factory: Callable[[], Any] | None = None,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
) -> None:
    conn = (connection_factory or get_connection)()
    try:
        with (unit_of_work_factory or _ConnectionUnitOfWork)(conn) as unit_of_work:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT id,storage_key FROM media_assets WHERE id=%s AND deleted_at IS NULL FOR UPDATE",
                    (asset_id,),
                )
                asset = cursor.fetchone()
                if not asset:
                    raise MediaAssetNotFoundError(f"找不到媒體資產 #{asset_id}")
                cursor.execute(
                    """
                    SELECT id FROM line_rich_menu_publications
                    WHERE image_asset_id=%s AND is_current=TRUE LIMIT 1
                    """,
                    (asset_id,),
                )
                legacy_published = cursor.fetchone() is not None
                cursor.execute(
                    "SELECT id FROM line_rich_menu_publication_tasks "
                    "WHERE image_object_reference=%s AND publication_status='published' LIMIT 1",
                    (asset["storage_key"],),
                )
                _require_media_not_published(legacy_published, cursor.fetchone() is not None)
                cursor.execute(
                    "UPDATE media_assets SET deleted_at=UTC_TIMESTAMP() WHERE id=%s",
                    (asset_id,),
                )
            unit_of_work.commit()
    finally:
        conn.close()


def _require_media_not_published(legacy_published: bool, canonical_published: bool):
    if legacy_published or canonical_published:
        raise MediaValidationError("目前已發布的 Rich Menu 圖片不能刪除")


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
