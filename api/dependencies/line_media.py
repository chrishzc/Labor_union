"""Concrete Rich Menu archive/read composition shared by API and worker."""
from api.dependencies.controlled_files import build_controlled_file_workflow
from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore, encode_line_png, render_rich_menu_image
from infrastructure.mysql.line_media_asset_query_repository import MySqlLineRichMenuMediaAssetQueryRepository, _asset
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.file.storage_layout import unified_storage_enabled
from subsystems.line import media_archive


def configure_rich_menu_archive():
    media_archive.get_connection = get_connection
    media_archive.controlled_file_workflow_factory = build_controlled_file_workflow
    media_archive.media_asset_writer_factory = MySqlLineRichMenuMediaAssetQueryRepository
    media_archive.media_asset_storage_provider = lambda: "nas" if unified_storage_enabled() else "local"
    media_archive.encode_line_png = encode_line_png
    media_archive.render_rich_menu_image = render_rich_menu_image


def _uploaded_reference(menu):
    appearance = menu["appearance"]
    row = media_archive.get_media_asset(appearance["image_asset_id"])
    asset = _asset(row, menu["id"])
    if (not asset.selectable or asset.sha256 != appearance.get("image_asset_sha256")
        or asset.asset_version.value != appearance.get("image_asset_version")):
        raise ValueError("Rich Menu frozen image asset has changed")
    return row["storage_key"]


def get_rich_menu_image_store(legacy_root):
    configure_rich_menu_archive()
    return FileSystemRichMenuImageStore(legacy_root,
        archive_generated=lambda menu: media_archive.store_generated_rich_menu_image(menu,
            created_by_admin_user_id=None, connection_factory=get_connection, unit_of_work_factory=MySqlUnitOfWork)["storage_key"],
        resolve_asset=_uploaded_reference, controlled_loader=media_archive.read_controlled_media)
