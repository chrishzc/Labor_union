"""One production root, write-time layout, and untouched legacy development data."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.file import storage_layout as layout
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.archive.contract_documents import archive_contract_document, read_archived_contract_document


@pytest.fixture
def nas_root(tmp_path, monkeypatch):
    root = tmp_path / "NAS 共用"
    root.mkdir()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(root))
    monkeypatch.setenv("CONTRACT_DOCUMENT_ARCHIVE_ROOT", str(tmp_path / "must-not-use-contracts"))
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path / "must-not-use-media"))
    return root


def test_all_runtime_roots_derive_from_one_setting_without_query_writes(nas_root):
    from api.dependencies.contract_signing import _archive_root
    from api.dependencies.contract_external_signing import _contract_archive_root, _controlled_file_storage_root
    from api.dependencies.contract_templates import get_contract_template_catalog
    from api.dependencies.line_worker_operation import _media_storage_root, _rich_menu_storage_root
    from api.routes.line_rich_menus import _menu_media_storage_root
    from subsystems.line.runtime_monitoring_application import _media_storage_root as monitored_root

    assert _archive_root() == _contract_archive_root() == nas_root / layout.ORDERS_DIRECTORY
    assert get_contract_template_catalog().root == nas_root / layout.ORDERS_DIRECTORY / "template-catalog"
    assert _controlled_file_storage_root() == nas_root
    assert _media_storage_root() == nas_root / layout.STAGING_DIRECTORY / "line_media"
    assert _rich_menu_storage_root() == nas_root / layout.MEDIA_DIRECTORY
    assert _menu_media_storage_root() == _rich_menu_storage_root()
    assert monitored_root() == nas_root
    assert not list(nas_root.iterdir())


def test_first_contract_write_builds_layout_and_keeps_case_and_integrity(nas_root):
    root = nas_root / layout.ORDERS_DIRECTORY
    result = archive_contract_document(b"synthetic contract", storage_root=root, storage_key="CASE-1/client/signed.pdf")
    assert all((nas_root / name).is_dir() for name in (*layout.BUSINESS_DIRECTORIES, layout.STAGING_DIRECTORY))
    assert (nas_root / layout.MEDIA_DIRECTORY / "rich_menus").is_dir()
    assert (root / "CASE-1/client/signed.pdf").read_bytes() == b"synthetic contract"
    assert read_archived_contract_document(storage_root=root, storage_key=result.storage_key, expected_sha256=result.sha256) == b"synthetic contract"


def test_new_staging_is_private_and_creates_named_categories(nas_root):
    storage = FileSystemControlledFileStorage(nas_root, settle_seconds=0)
    result = storage.put_staged(idempotency_key="fixture:stage", filename="履歷.pdf", mime_type="application/pdf", content=b"synthetic resume")
    assert (nas_root / layout.STAGING_DIRECTORY / "objects").is_dir()
    assert not (nas_root / ".controlled-file-staging").exists()
    assert storage.read_staged(result.staging_id, expected_sha256=result.sha256_digest).content == b"synthetic resume"
    assert storage.discover(limit=10).items == ()
    assert all((nas_root / name).is_dir() for name in layout.BUSINESS_DIRECTORIES)


def test_new_menu_and_unassociated_line_media_use_the_shared_root(nas_root, monkeypatch):
    from infrastructure.line import rich_menu_image_store as menus
    from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
    from api.dependencies.line_worker_operation import _media_storage_root, _rich_menu_storage_root
    monkeypatch.setattr(menus, "render_rich_menu_image", lambda *_: b"synthetic menu image")
    store = menus.FileSystemRichMenuImageStore(_rich_menu_storage_root())
    media = FileSystemLineMediaObjectStore(_media_storage_root())
    assert not list(nas_root.iterdir())
    reference = store.materialize("{}")
    assert reference.startswith("rich_menus/")
    assert store.load(reference)[0] == b"synthetic menu image"
    content = b"synthetic pending media"
    metadata = SimpleNamespace(content_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content),
                               content_type="image/jpeg", category=SimpleNamespace(value="user_upload"))
    media_reference = media.put(metadata, content)
    assert (nas_root / layout.STAGING_DIRECTORY / "line_media" / media_reference).read_bytes() == content
    assert not (nas_root.parent / "must-not-use-media").exists()


def test_uploaded_menu_background_is_readable_by_the_menu_publisher(nas_root):
    from domains.line.media import LineMediaCategory
    from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore
    from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
    from api.dependencies.line_worker_operation import _media_storage_root, _rich_menu_storage_root
    content = b"synthetic uploaded menu background"
    metadata = SimpleNamespace(content_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content),
        content_type="image/png", category=LineMediaCategory.RICH_MENU_IMAGE)
    reference = FileSystemLineMediaObjectStore(_media_storage_root()).put(metadata, content)
    assert reference.startswith("rich_menus/")
    assert FileSystemRichMenuImageStore(_rich_menu_storage_root()).load(reference) == (content, "image/png")
    assert not (nas_root / layout.STAGING_DIRECTORY / "line_media" / reference).exists()


def test_management_menu_asset_upload_uses_the_same_root_and_readable_key(nas_root, monkeypatch):
    from api.routes import line_rich_menus  # Configures the subsystem's concrete storage ports.
    from subsystems.line import media_archive
    from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore
    calls = []
    class Cursor:
        lastrowid = 42
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append(parameters)
    connection = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: None, rollback=lambda: None, close=lambda: None)
    monkeypatch.setattr(media_archive, "get_media_asset", lambda identity: {"id": identity, "storage_key": calls[0][2]})
    content = b"synthetic management menu asset"
    asset = media_archive._save_asset(content, menu_id="staff", original_filename="fixture.jpg", width=2500, height=1686,
        created_by_admin_user_id=17, generated=False, connection_factory=lambda: connection)
    assert asset["storage_key"].startswith("rich_menus/staff/")
    assert calls[0][1] == "nas"
    assert FileSystemRichMenuImageStore(line_rich_menus._menu_media_storage_root()).load(asset["storage_key"])[0] == content
    assert not (nas_root.parent / "must-not-use-media").exists()


def test_unavailable_root_never_creates_root_or_uses_deprecated_settings(nas_root, monkeypatch):
    missing = nas_root / "offline-share"
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(missing))
    with pytest.raises(layout.StorageLayoutError, match="不會自動建立根目錄"):
        archive_contract_document(b"fixture", storage_root=missing / layout.ORDERS_DIRECTORY, storage_key="CASE-1/test.pdf")
    assert not missing.exists()
    monkeypatch.delenv("CONTROLLED_FILE_STORAGE_ROOT")
    with pytest.raises(layout.StorageLayoutError, match="未改存本機"):
        layout.component_storage_root(layout.ORDERS_DIRECTORY, legacy_variable="CONTRACT_DOCUMENT_ARCHIVE_ROOT", development_default=missing)
    assert not (nas_root.parent / "must-not-use-contracts").exists()


def test_development_explicit_roots_and_existing_data_are_unchanged(nas_root, monkeypatch):
    from api.dependencies.contract_signing import _archive_root
    from api.dependencies.line_worker_operation import _media_storage_root, _rich_menu_storage_root
    monkeypatch.setenv("APP_ENV", "development")
    original = nas_root.parent / "must-not-use-contracts"
    original.mkdir()
    sentinel = original / "existing.bin"
    sentinel.write_bytes(b"old development bytes")
    assert _archive_root() == original
    assert _media_storage_root() == _rich_menu_storage_root() == nas_root.parent / "must-not-use-media"
    assert sentinel.read_bytes() == b"old development bytes"
    assert not list(nas_root.iterdir())
    assert not layout.unified_storage_enabled()


def test_old_staging_bytes_and_idempotency_replay_are_read_without_migration(nas_root):
    storage = FileSystemControlledFileStorage(nas_root)
    options = dict(idempotency_key="fixture:old-stage", filename="existing.pdf", mime_type="application/pdf", content=b"legacy fixture")
    original = storage.put_staged(**options)
    (nas_root / layout.STAGING_DIRECTORY).rename(nas_root / ".controlled-file-staging")
    legacy_files = {path: path.read_bytes() for path in (nas_root / ".controlled-file-staging").rglob("*") if path.is_file()}
    assert storage.read_registered_staged(original.staging_id, expected_sha256=original.sha256_digest).content == b"legacy fixture"
    replayed = storage.put_staged(**options)
    assert replayed.staging_id == original.staging_id
    assert {path: path.read_bytes() for path in legacy_files} == legacy_files


def test_linked_category_is_blocked_before_writing_outside_root(nas_root, monkeypatch):
    original = Path.is_junction
    blocked = nas_root / layout.ORDERS_DIRECTORY
    monkeypatch.setattr(Path, "is_junction", lambda path: path == blocked or original(path))
    with pytest.raises(layout.StorageLayoutError, match="轉接點"):
        archive_contract_document(b"fixture", storage_root=blocked, storage_key="CASE-1/test.pdf")
    assert not blocked.exists()
