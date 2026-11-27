from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from errno import EIO
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.dependencies.admin_auth import require_admin
from api.routes import staff_web_profile as route
from domains.staff.web_profile import PublishedWebProfilePhoto, WebProfileCategory, WebProfileTemplateItem
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.storage_layout import STAGING_DIRECTORY
from shared_kernel.clock import FixedBusinessClock
from subsystems.controlled_files.workflow import (
    ControlledFileDownloadReference,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileWorkflow,
    ControlledFileWorkflowRepository,
)
from subsystems.staff.web_profile import StaffWebProfile, WebProfileRepository


_NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
_STAFF = 7
_ITEM = WebProfileTemplateItem(42, 1, "Fixture item", WebProfileCategory.PHOTO, 1)
_PATH = "/api/v1/admin/staff-web-profile/7/website/integrity"


@dataclass
class PhotoFixture:
    root: Path
    staff: Mock
    registered: Mock
    storage: FileSystemControlledFileStorage
    uow: Mock
    client: TestClient
    app: FastAPI
    files: dict[str, ControlledFileDownloadReference]
    image: bytes

    def store(
        self, number: int, *, crop_of: str | None = None, content: bytes | None = None, finalize: bool = True,
    ) -> str:
        file_id = f"cf_{number:032x}"
        staged = self.storage.put_staged(
            idempotency_key=f"fixture-photo-{number}", filename="private-synthetic.png",
            mime_type="image/png", content=self.image if content is None else content,
        )
        if finalize:
            self.storage.finalize_staged(
                staged.staging_id, expected_sha256=staged.sha256_digest, object_reference=f"fixture/{file_id}.png",
            )
        folder = "staff-web/original" if crop_of is None else f"staff-web/crop/{crop_of}"
        self.files[file_id] = ControlledFileDownloadReference(
            ControlledFileReadback(
                file_id, ControlledFileOwner.STAFF, ControlledFilePurpose.STAFF_PROFILE_PHOTO, str(_STAFF),
                "private-synthetic.png", folder, 1, staged.sha256_digest, "image/png",
                staged.size_bytes, "active", _NOW,
            ),
            staged.staging_id,
        )
        return file_id

    def payload(self, file_id: str) -> Path:
        return self.root / "fixture" / f"{file_id}.png"

    def staging_path(self, file_id: str, filename: str) -> Path:
        staging_id = self.files[file_id].staging_id
        return self.root / STAGING_DIRECTORY / "objects" / staging_id[:2] / staging_id / filename

    def update_readback(self, file_id: str, **changes: object) -> None:
        reference = self.files[file_id]
        self.files[file_id] = replace(reference, readback=replace(reference.readback, **changes))

    def allow_reader(self) -> None:
        principal = SimpleNamespace(id=_STAFF, effective_capabilities=lambda: frozenset({"data_browser.read"}))
        self.app.dependency_overrides[require_admin] = lambda: principal

    def report(self, *photos: PublishedWebProfilePhoto) -> list[dict[str, object]]:
        self.staff.current.return_value = photos
        result = self.client.get(_PATH)
        assert result.status_code == 200, result.text
        assert result.headers["Cache-Control"] == "private, no-store"
        assert result.headers["X-Content-Type-Options"] == "nosniff"
        data = result.json()["data"]
        assert set(data) == {"staff_id", "photos"}
        assert data["staff_id"] == _STAFF
        assert "private-synthetic" not in result.text
        return data["photos"]


@pytest.fixture
def photos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[PhotoFixture]:
    root = tmp_path / "private-synthetic"
    root.mkdir()
    storage = FileSystemControlledFileStorage(root)
    staff = Mock(spec=WebProfileRepository)
    staff.staff_name.side_effect = lambda staff_id: "Private Staff" if staff_id == _STAFF else None
    registered = Mock(spec=ControlledFileWorkflowRepository)
    files: dict[str, ControlledFileDownloadReference] = {}
    registered.get_readback.side_effect = lambda file_id: files[file_id].readback if file_id in files else None
    registered.get_download_reference.side_effect = files.get
    uow = Mock(side_effect=AssertionError("read-only query opened a mutation unit of work"))
    controlled = ControlledFileWorkflow(registered, storage, uow, FixedBusinessClock(_NOW))
    web = StaffWebProfile(staff, lambda: controlled, uow)

    @contextmanager
    def application() -> Iterator[StaffWebProfile]:
        yield web

    monkeypatch.setattr(route, "staff_web_profile_application", application)
    app = FastAPI()
    app.include_router(route.router)
    with BytesIO() as output:
        Image.new("RGB", (4, 3), "green").save(output, "PNG")
        image = output.getvalue()
    with TestClient(app) as client:
        yield PhotoFixture(root, staff, registered, storage, uow, client, app, files, image)
    uow.assert_not_called()


def _published(entry_id: int, file_id: str, *, version: int = 1, crop: str | None = None) -> PublishedWebProfilePhoto:
    return PublishedWebProfilePhoto(entry_id, version, _STAFF, _ITEM, file_id, crop, None)


def _outcome(entry_id: int, status: str, reason: str, *, version: int = 1) -> dict[str, object]:
    return {"entry_id": entry_id, "version": version, "status": status, "reason": reason}


def test_integrity_requires_registry_read_and_checks_only_the_published_snapshot(photos: PhotoFixture) -> None:
    original = photos.store(1)
    crop = photos.store(2, crop_of=original)
    previously_published = photos.store(3)
    pending = photos.store(4)
    removed = photos.store(5)
    current = photos.store(6)
    for not_selected in (original, previously_published, pending, removed):
        photos.payload(not_selected).unlink()
    published_crop = _published(12, original, version=4, crop=crop)
    published_original = _published(13, current)
    photos.staff.current.return_value = (published_crop, published_original)

    assert photos.client.get(_PATH).status_code == 401
    unauthorized = SimpleNamespace(id=_STAFF, effective_capabilities=lambda: frozenset())
    photos.app.dependency_overrides[require_admin] = lambda: unauthorized
    assert photos.client.get(_PATH).status_code == 403
    assert photos.staff.mock_calls == photos.registered.mock_calls == []

    photos.allow_reader()
    before = {path: path.read_bytes() for path in photos.root.rglob("*") if path.is_file()}
    report = photos.report(published_crop, published_original)
    assert report == [_outcome(12, "ok", "verified", version=4), _outcome(13, "ok", "verified")]
    assert photos.staff.mock_calls == [call.staff_name(_STAFF), call.current(_STAFF)]
    assert photos.registered.mock_calls == [
        call.get_readback(crop), call.get_download_reference(crop),
        call.get_readback(current), call.get_download_reference(current),
    ]
    assert {path: path.read_bytes() for path in photos.root.rglob("*") if path.is_file()} == before

    photos.payload(original).write_bytes(photos.image)
    photos.payload(crop).unlink()
    photos.registered.reset_mock()
    assert photos.report(published_crop) == [_outcome(12, "missing", "payload_missing", version=4)]
    assert photos.registered.mock_calls == [call.get_readback(crop), call.get_download_reference(crop)]
    assert photos.payload(original).read_bytes() == photos.image


def test_integrity_separates_confirmed_missing_digest_size_and_decode_failures(photos: PhotoFixture) -> None:
    photos.allow_reader()
    missing, digest_changed, size_changed, wrong_recorded_size, invalid_image, healthy = (
        photos.store(10), photos.store(11), photos.store(12), photos.store(13),
        photos.store(14, content=b"not an image"), photos.store(15, finalize=False),
    )
    photos.payload(missing).unlink()
    photos.payload(digest_changed).write_bytes(bytes([photos.image[0] ^ 1]) + photos.image[1:])
    photos.payload(size_changed).write_bytes(photos.image[:-1])
    photos.update_readback(wrong_recorded_size, size_bytes=len(photos.image) + 1)

    assert photos.report(*(
        _published(index, file_id) for index, file_id in enumerate(
            (missing, digest_changed, size_changed, wrong_recorded_size, invalid_image, healthy), start=20,
        )
    )) == [
        _outcome(20, "missing", "payload_missing"),
        _outcome(21, "mismatch", "bytes_mismatch"),
        _outcome(22, "mismatch", "bytes_mismatch"),
        _outcome(23, "mismatch", "bytes_mismatch"),
        _outcome(24, "mismatch", "invalid_image"),
        _outcome(25, "ok", "verified"),
    ]


def test_integrity_reports_permission_io_and_disappearing_reads_as_unavailable(
    photos: PhotoFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    photos.allow_reader()
    permission, io, vanished, healthy = (photos.store(number) for number in range(21, 25))
    original_read = Path.read_bytes
    failures = {
        photos.payload(permission): PermissionError("private-synthetic permission failure"),
        photos.payload(io): OSError(EIO, "private-synthetic I/O failure"),
        photos.payload(vanished): FileNotFoundError("private-synthetic read race"),
    }

    def read(path: Path) -> bytes:
        if path in failures:
            raise failures[path]
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    assert photos.report(*(
        _published(index, file_id) for index, file_id in enumerate((permission, io, vanished, healthy), start=30)
    )) == [
        _outcome(30, "unavailable", "read_unconfirmed"),
        _outcome(31, "unavailable", "read_unconfirmed"),
        _outcome(32, "unavailable", "read_unconfirmed"),
        _outcome(33, "ok", "verified"),
    ]


def test_integrity_reports_unavailable_root_and_mount_disappearance_as_unavailable(
    photos: PhotoFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    photos.allow_reader()
    file_id = photos.store(31)
    original_resolve = photos.storage._resolve_target
    old_mount = photos.root.with_name("old-mount")

    def resolve(root: Path, reference: PurePosixPath) -> Path:
        root.rename(old_mount)
        root.mkdir()
        return original_resolve(root, reference)

    monkeypatch.setattr(photos.storage, "_resolve_target", resolve)
    assert photos.report(_published(40, file_id)) == [_outcome(40, "unavailable", "read_unconfirmed")]
    photos.root.rmdir()
    assert photos.report(_published(40, file_id)) == [_outcome(40, "unavailable", "read_unconfirmed")]
    assert (old_mount / "fixture" / f"{file_id}.png").read_bytes() == photos.image


def test_integrity_keeps_missing_metadata_and_unconfirmed_staging_distinct_from_missing_payload(
    photos: PhotoFixture,
) -> None:
    photos.allow_reader()
    file_metadata_missing = f"cf_{41:032x}"
    staging_metadata_missing = photos.store(42, finalize=False)
    staging_payload_missing = photos.store(43, finalize=False)
    download_reference_missing = photos.store(44)
    malformed_finalized_locator = photos.store(45)
    photos.staging_path(staging_metadata_missing, "metadata.json").unlink()
    photos.staging_path(staging_payload_missing, "payload.bin").unlink()
    metadata_path = photos.staging_path(malformed_finalized_locator, "metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["finalized_object_reference"] = 123
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    photos.registered.get_download_reference.side_effect = (
        lambda file_id: None if file_id == download_reference_missing else photos.files[file_id]
    )

    assert photos.report(*(
        _published(index, file_id) for index, file_id in enumerate(
            (file_metadata_missing, staging_metadata_missing, staging_payload_missing, download_reference_missing,
             malformed_finalized_locator),
            start=50,
        )
    )) == [_outcome(index, "unavailable", "read_unconfirmed") for index in range(50, 55)]


def test_integrity_rejects_wrong_file_owner_purpose_staff_and_crop_source_before_download(photos: PhotoFixture) -> None:
    photos.allow_reader()
    wrong_owner, wrong_purpose, wrong_staff, wrong_source = (photos.store(number) for number in range(51, 55))
    photos.update_readback(wrong_owner, owner=ControlledFileOwner.ORDERS)
    photos.update_readback(wrong_purpose, purpose=ControlledFilePurpose.STAFF_RESUME)
    photos.update_readback(wrong_staff, subject_reference="8")
    photos.update_readback(wrong_source, logical_folder=f"staff-web/crop/{wrong_owner}")

    assert photos.report(
        _published(60, wrong_owner), _published(61, wrong_purpose), _published(62, wrong_staff),
        _published(63, wrong_purpose, crop=wrong_source),
    ) == [_outcome(index, "mismatch", "reference_mismatch") for index in range(60, 64)]
    photos.registered.get_download_reference.assert_not_called()


def test_integrity_returns_an_empty_snapshot_and_distinguishes_an_unknown_staff_member(photos: PhotoFixture) -> None:
    photos.allow_reader()
    assert photos.report() == []
    response = photos.client.get(_PATH.replace("/7/", "/8/"))
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "staff_web_staff_not_found"
    assert photos.staff.mock_calls == [call.staff_name(_STAFF), call.current(_STAFF), call.staff_name(8)]
    assert photos.registered.mock_calls == []
