"""Real media workflow/PNG and immutable owner projections; never execute SQL."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineRichMenuPublicationId
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore, encode_line_png
from infrastructure.mysql.line_media_asset_query_repository import _controlled_file_reference
from infrastructure.mysql.line_configuration_publication_repository import _controlled_image_publication_matches
from infrastructure.db.controlled_file_repository import _rich_menu_reference_status
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import FixedBusinessClock
from subsystems.line import media_archive
from subsystems.line.ports import LineRichMenuPublicationStep
from subsystems.line.rich_menu_contracts import LineRichMenuProviderRequest
from subsystems.line.rich_menu_worker import rich_menu_step_fingerprint
from subsystems.controlled_files.workflow import ControlledFileWorkflow, ControlledFileStagingFacts, ControlledFileIntent, ControlledFileReadback, ControlledFileCommandClaim, ControlledFileDownloadReference, ControlledFileOwner, ControlledFilePurpose
from subsystems.controlled_files.contracts import ControlledFileStagingRegistrationStatus

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
FILE = "cf_" + "a"*32


class NoSqlConnection:
    def __init__(self): self.events = []
    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")
    def close(self): self.events.append("close")
    def cursor(self, *args): raise AssertionError("project SQL is forbidden")


class ControlledPort:
    def __init__(self, connection): self.connection, self.receipt, self.readback = connection, None, None
    def register_staging(self, command, result, **kwargs):
        self.connection.events.append("stage")
        if hasattr(self, "facts") and self.facts.staging.staging_id == result.staging_id:
            return result
        self.facts = ControlledFileStagingFacts(result, 1, ControlledFileStagingRegistrationStatus.UNREGISTERED,
            ControlledFileIntent(result.staging_id, command.owner, command.purpose, command.subject_reference, command.object_key, command.logical_folder))
        return result
    def load_staging(self, staging_id, *, for_update): return self.facts
    def owner_subject_exists(self, intent, *, for_update): return True
    def find_receipt(self, *args, **kwargs): return self.receipt
    def claim_command(self, *args): return ControlledFileCommandClaim.CREATED
    def register_file(self, candidate, *, actor, applied_at):
        self.connection.events.append("controlled_object")
        self.readback = ControlledFileReadback(FILE, candidate.owner, candidate.purpose, candidate.subject_reference,
            candidate.filename, candidate.logical_folder, 1, candidate.sha256_digest, candidate.mime_type, candidate.size_bytes, "registered", applied_at)
        return self.readback
    def mark_staging_registered(self, *args, **kwargs):
        self.facts = replace(self.facts, registration_status=ControlledFileStagingRegistrationStatus.REGISTERED)
    def save_receipt(self, key, receipt, correlation): self.receipt = receipt
    def save_post_commit_finalize_intent(self, intent): self.connection.events.append("finalize_intent")
    def get_readback(self, file_id): return self.readback
    def get_download_reference(self, file_id): return ControlledFileDownloadReference(self.readback, self.facts.staging.staging_id)


def wire_archive(monkeypatch, tmp_path, *, fail=False):
    connection = NoSqlConnection()
    port = ControlledPort(connection)
    workflow = ControlledFileWorkflow(port, FileSystemControlledFileStorage(tmp_path),
        lambda: MySqlUnitOfWork(connection), FixedBusinessClock(NOW))
    assets = {}
    class MetadataPort:
        def find_generated_asset(self, identity, menu_id, **kwargs):
            if getattr(port, "hide_next_lookup", False):
                port.hide_next_lookup = False
                return None
            return assets.get("asset:" + identity)
        def register_controlled_asset(self, readback, **kwargs):
            assert readback is port.readback and port.receipt is not None
            connection.events.append("media_fk")
            if fail: raise ValueError("synthetic metadata failure")
            asset = {"id": 1, "category": "rich_menu", "owner_type": "line_menu", "owner_id": kwargs["menu_id"],
                "controlled_file_object_id": 1, "controlled_file_id": readback.file_id, "storage_key": readback.file_id,
                "sha256": readback.sha256_digest, "file_size": readback.size_bytes, "mime_type": readback.mime_type,
                "storage_provider": kwargs["storage_provider"], "width": kwargs["width"], "height": kwargs["height"],
                "created_at": NOW, "deleted_at": None, "original_filename": readback.filename}
            assets[port.facts.stored_intent.object_key] = asset
            return asset
    def workflow_factory(actual):
        assert actual is connection
        return workflow
    def metadata_factory(actual):
        assert actual is connection
        return MetadataPort()
    monkeypatch.setattr(media_archive, "controlled_file_workflow_factory", workflow_factory)
    monkeypatch.setattr(media_archive, "media_asset_writer_factory", metadata_factory)
    monkeypatch.setattr(media_archive, "encode_line_png", encode_line_png)
    monkeypatch.setattr(media_archive, "media_asset_storage_provider", lambda: "local")
    return connection, workflow, port


def png():
    return encode_line_png(Image.new("RGB", (2500, 843), "white"))


def test_upload_actual_workflow_binds_media_fk_before_single_outer_commit(monkeypatch, tmp_path):
    connection, workflow, port = wire_archive(monkeypatch, tmp_path)
    content = png()
    asset = media_archive.store_uploaded_rich_menu_image(content, menu_id="staff", original_filename="menu.jpg",
        expected_width=2500, expected_height=843, created_by_admin_user_id=7,
        connection_factory=lambda: connection, unit_of_work_factory=MySqlUnitOfWork)
    assert asset["storage_key"] == FILE and asset["controlled_file_object_id"] == 1
    assert asset["storage_provider"] == "local"
    assert port.readback.mime_type == "image/png" and port.readback.filename == "menu.png"
    assert workflow.download(FILE).content == content
    assert connection.events == ["begin", "stage", "commit", "begin", "controlled_object", "finalize_intent", "media_fk", "commit", "close"]
    # First commit is provisional staging; formal object/FK have one outer owner.
    assert port.receipt.receipt.readback.sha256_digest == sha256(content).hexdigest()


def test_generated_same_png_replays_one_formal_file_and_media_binding(monkeypatch, tmp_path):
    connection, _, port = wire_archive(monkeypatch, tmp_path)
    monkeypatch.setattr(media_archive, "render_rich_menu_image", lambda _: png())
    menu = {"id": "staff", "size": {"width": 2500, "height": 843}}
    def materialize():
        return media_archive.store_generated_rich_menu_image(menu, created_by_admin_user_id=None,
            connection_factory=lambda: connection, unit_of_work_factory=MySqlUnitOfWork)
    first = materialize()
    second = materialize()
    assert first is second and first["storage_key"] == FILE
    assert connection.events.count("stage") == connection.events.count("controlled_object") == connection.events.count("media_fk") == 1
    # Interleave another materializer after its first read but before fresh
    # Preview: the already-registered stage must replay its exact committed FK.
    port.hide_next_lookup = True
    assert materialize() is first
    assert connection.events.count("controlled_object") == connection.events.count("media_fk") == 1
    # A corrupt identity must be rejected rather than manufacturing a new file.
    first["storage_key"] = "cf_" + "d"*32
    with pytest.raises(media_archive.MediaValidationError, match="識別"):
        materialize()
    assert connection.events.count("controlled_object") == 1


def test_metadata_failure_rolls_back_formal_outer_transaction_without_second_commit(monkeypatch, tmp_path):
    connection, _, _ = wire_archive(monkeypatch, tmp_path, fail=True)
    with pytest.raises(ValueError, match="synthetic metadata failure"):
        media_archive.store_uploaded_rich_menu_image(png(), menu_id="staff", original_filename="menu.png",
            expected_width=2500, expected_height=843, created_by_admin_user_id=7,
            connection_factory=lambda: connection, unit_of_work_factory=MySqlUnitOfWork)
    assert connection.events[-3:] == ["media_fk", "rollback", "close"]
    assert connection.events.count("commit") == 1


def test_new_controlled_media_reader_uses_fk_identity_and_original_verified_download(monkeypatch, tmp_path):
    connection, _, _ = wire_archive(monkeypatch, tmp_path)
    content = png()
    asset = media_archive.store_uploaded_rich_menu_image(content, menu_id="staff", original_filename="menu.png",
        expected_width=2500, expected_height=843, created_by_admin_user_id=7,
        connection_factory=lambda: connection, unit_of_work_factory=MySqlUnitOfWork)
    monkeypatch.setattr(media_archive, "get_media_asset", lambda *args, **kwargs: asset)
    _, observed = media_archive.read_media_asset(1, connection_factory=lambda: connection)
    assert observed == content
    asset["controlled_file_id"] = "cf_" + "b"*32
    with pytest.raises(media_archive.MediaValidationError, match="識別"):
        media_archive.read_media_asset(1, connection_factory=lambda: connection)


def test_materializer_calls_controlled_archive_and_keeps_legacy_reads(tmp_path):
    calls = []
    store = FileSystemRichMenuImageStore(tmp_path,
        archive_generated=lambda menu: calls.append(menu["id"]) or FILE,
        controlled_loader=lambda ref: (b"PNG", "image/png"))
    definition = canonical_line_payload_json({"id": "staff", "appearance": {"image_mode": "generated"}})
    assert store.materialize(definition) == FILE and calls == ["staff"]
    assert store.materialize(definition, FILE) == FILE and calls == ["staff"]
    assert store.materialize(definition, "rich_menu/unresolved") == FILE and calls == ["staff", "staff"]
    legacy = tmp_path / "rich_menus" / "legacy.jpg"; legacy.parent.mkdir(); legacy.write_bytes(b"old")
    assert store.load("rich_menus/legacy.jpg") == (b"old", "image/jpeg")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["rich_menus"]


def menu():
    from subsystems.line.rich_menu_models import RichMenuDefinition
    return RichMenuDefinition.model_validate({"id": "staff", "name": "Staff", "audience_role": "staff",
        "chat_bar_text": "Menu", "buttons": [{"id": "home", "label": "Home",
        "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843}, "action": {"type": "message", "text": "Home"}}]})


def test_actual_generated_preview_png_header_and_bytes_have_zero_archive_effect(monkeypatch):
    from api.routes import line_rich_menus as route
    monkeypatch.setattr(media_archive, "controlled_file_workflow_factory", lambda _: pytest.fail("preview must not create files"))
    monkeypatch.setattr(route, "read_media_asset", lambda _: pytest.fail("generated preview must not query DB"))
    response = route.preview_rich_menu(menu())
    assert response.media_type == "image/png" and response.body.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("mime_type", ["image/png", "image/jpeg"])
def test_uploaded_preview_uses_actual_new_or_legacy_mime(monkeypatch, mime_type):
    from api.routes import line_rich_menus as route
    candidate = menu().model_dump(mode="json")
    candidate["appearance"] = {"image_mode": "uploaded", "image_asset_id": 1,
        "image_asset_sha256": "a"*64, "image_asset_version": "b"*64}
    monkeypatch.setattr(route, "read_media_asset", lambda _: ({"mime_type": mime_type}, b"immutable-image"))
    response = route.preview_rich_menu(type(menu()).model_validate(candidate))
    assert response.media_type == mime_type and response.body == b"immutable-image"


def reference_row():
    digest = "c"*64
    return {"id": 1, "owner_id": "staff", "subject_reference": "staff", "storage_key": FILE,
        "opaque_object_id": FILE, "version_number": 1, "sha256": digest, "content_sha256": digest,
        "file_size": 3, "size_bytes": 3, "mime_type": "image/png", "content_type": "image/png", "deleted_at": None}


@pytest.mark.parametrize("field,value,matched", [(None,None,True), ("storage_key","same-name.png",False),
    ("owner_id","customer",False), ("sha256","d"*64,False), ("file_size",4,False), ("mime_type","image/jpeg",False)])
def test_actual_media_owner_projection_needs_exact_fk_bound_identity_and_facts(field, value, matched):
    row = reference_row()
    if field: row[field] = value
    assert (_controlled_file_reference(row) is not None) is matched


def publication_row(reference):
    definition = canonical_line_payload_json({"id": "staff", "appearance": {"image_mode": "generated"}})
    request = LineRichMenuProviderRequest(LineRichMenuPublicationId(7), definition, reference.file_id)
    fingerprint = rich_menu_step_fingerprint(request, LineRichMenuPublicationStep.UPLOAD, "provider-menu").value
    return {"id": 7, "menu_definition_id": "staff", "publication_status": "published", "definition_snapshot": definition,
        "image_object_reference": FILE, "provider_menu_id": "provider-menu", "acknowledged_provider_menu_id": "provider-menu",
        "request_fingerprint": fingerprint}


@pytest.mark.parametrize("field,value,matched", [(None,None,True), ("request_fingerprint","d"*64,False),
    ("publication_status","queued",False), ("image_object_reference","cf_"+"d"*32,False),
    ("acknowledged_provider_menu_id","other-provider-menu",False), ("menu_definition_id","customer",False),
    ("definition_snapshot", "[]", False), ("definition_snapshot", "{malformed", False)])
def test_true_published_upload_acknowledgement_binds_original_saga_request(field, value, matched):
    reference = _controlled_file_reference(reference_row())
    row = publication_row(reference)
    if field: row[field] = value
    assert _controlled_image_publication_matches(row, reference) is matched


def test_real_api_worker_composition_uses_controlled_archive_and_frozen_uploaded_owner(monkeypatch, tmp_path):
    from api.dependencies import line_media as composition
    from infrastructure.mysql.line_media_asset_query_repository import _asset
    connection, workflow, port = wire_archive(monkeypatch, tmp_path)
    monkeypatch.setattr(composition, "get_connection", lambda: connection)
    monkeypatch.setattr(composition, "build_controlled_file_workflow", media_archive.controlled_file_workflow_factory)
    monkeypatch.setattr(composition, "MySqlLineRichMenuMediaAssetQueryRepository", media_archive.media_asset_writer_factory)
    monkeypatch.setattr(composition, "unified_storage_enabled", lambda: False)
    store = composition.get_rich_menu_image_store(tmp_path / "legacy")
    definition = menu().model_dump(mode="json")
    assert store.materialize(canonical_line_payload_json(definition)) == FILE
    data, mime = store.load(FILE)
    assert mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")
    assert not (tmp_path / "legacy").exists()
    asset = {"id": 1, "category": "rich_menu", "owner_type": "line_menu", "owner_id": "staff", "original_filename": "menu.png",
        "mime_type": "image/png", "file_size": port.readback.size_bytes, "sha256": port.readback.sha256_digest,
        "width": 2500, "height": 843, "created_at": NOW, "deleted_at": None, "storage_key": FILE}
    monkeypatch.setattr(media_archive, "get_media_asset", lambda _: asset)
    definition["appearance"] = {"image_mode": "uploaded", "image_asset_id": 1,
        "image_asset_sha256": asset["sha256"], "image_asset_version": _asset(asset, "staff").asset_version.value}
    assert store.materialize(canonical_line_payload_json(definition)) == FILE
    definition["appearance"]["image_asset_sha256"] = "d"*64
    with pytest.raises(ValueError, match="has changed"):
        store.materialize(canonical_line_payload_json(definition))
    assert connection.events.count("controlled_object") == connection.events.count("media_fk") == 1


def test_true_line_owner_and_outbound_make_same_file_reconciliation_complete():
    reference = _controlled_file_reference(reference_row())
    readback = ControlledFileReadback(FILE, ControlledFileOwner.LINE_INTEGRATION, ControlledFilePurpose.RICH_MENU_BACKGROUND,
        "staff", "menu.png", "line/rich-menus/staff", 1, "c"*64, "image/png", 3, "registered", NOW)
    published = _controlled_image_publication_matches(publication_row(reference), reference)
    assert _rich_menu_reference_status(readback, reference, published) == {"business_reference": "matched", "outbound_reference": "matched"}
    assert _rich_menu_reference_status(replace(readback, version=2), reference, published)["business_reference"] == "mismatch"


def test_actual_archive_to_owner_adapter_to_maintenance_readback_has_all_four_worlds(monkeypatch, tmp_path):
    from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
    from infrastructure.mysql import line_media_asset_query_repository as media_owner
    from infrastructure.mysql import line_configuration_publication_repository as publication_owner
    from subsystems.controlled_files.maintenance import ControlledFileMaintenanceApplication
    from shared_kernel.identities import ActorContext, CorrelationId
    connection, workflow, port = wire_archive(monkeypatch, tmp_path)
    asset = media_archive.store_uploaded_rich_menu_image(png(), menu_id="staff", original_filename="menu.png",
        expected_width=2500, expected_height=843, created_by_admin_user_id=7,
        connection_factory=lambda: connection, unit_of_work_factory=MySqlUnitOfWork)
    row = reference_row() | {"sha256": asset["sha256"], "content_sha256": port.readback.sha256_digest,
        "file_size": asset["file_size"], "size_bytes": port.readback.size_bytes}
    reference = _controlled_file_reference(row)
    assert reference is not None
    actual = MySqlControlledFileWorkflowRepository(connection)
    actual.get_download_reference = port.get_download_reference
    def media_factory(conn):
        assert conn is connection
        return SimpleNamespace(get_controlled_file_reference=lambda file_id: _controlled_file_reference(row))
    def publication_factory(conn):
        assert conn is connection
        return SimpleNamespace(controlled_image_publication_matches=lambda ref: _controlled_image_publication_matches(publication_row(ref), ref))
    monkeypatch.setattr(media_owner, "MySqlLineRichMenuMediaAssetQueryRepository", media_factory)
    monkeypatch.setattr(publication_owner, "MySqlLineRichMenuPublicationRepository", publication_factory)
    port.reconciliation_reference_status = actual.reconciliation_reference_status
    service = ControlledFileMaintenanceApplication(port, workflow._storage, lambda: MySqlUnitOfWork(connection), FixedBusinessClock(NOW))
    before = list(connection.events)
    result = service.reconcile(FILE, actor=ActorContext("admin:7"), correlation_id=CorrelationId("four-worlds"))
    assert result["complete"] and result["storage_outcome"] == "exact"
    assert connection.events == before  # Preview uses no transaction/writes/provider.


@pytest.mark.parametrize("legacy,canonical", [(False,False),(True,False),(False,True),(True,True)])
def test_soft_delete_original_guard_protects_both_real_publication_owners(legacy, canonical):
    if legacy or canonical:
        with pytest.raises(media_archive.MediaValidationError, match="已發布"):
            media_archive._require_media_not_published(legacy, canonical)
    else:
        media_archive._require_media_not_published(legacy, canonical)
