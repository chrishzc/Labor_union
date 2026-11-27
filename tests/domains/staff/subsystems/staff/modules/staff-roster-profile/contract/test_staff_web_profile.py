from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timezone
from io import BytesIO
import os
from random import Random
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from redis import Redis

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_web_profile import build_staff_web_profile
from api.routes import staff_profile_change as intake
from api.routes import staff_web_profile as route
from domains.line.identities import LineUserId
from domains.line.identity_binding import LineIdentityBindingStatus
from domains.staff.retirement import StaffLifecycleState
from domains.staff.web_profile import (
    PublishedWebProfilePhoto,
    ReminderLead,
    WebProfileCategory,
    WebProfileConflict,
    WebProfileEntryVersion,
    WebProfilePhoto,
    WebProfileTemplateItem,
)
from infrastructure.redis.staff_profile_change_staging import StaffProfileChangeStaging
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, ExpectedVersion
from subsystems.controlled_files.workflow import ControlledFileOwner, ControlledFilePurpose
from subsystems.line import staff_web_expiry_reminders as reminders
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
from subsystems.staff.profile_change_approval import StaffProfileChangeApproval, restore_staff_profile_change
from subsystems.staff.web_profile import StaffWebProfile, encode_web_photo


ORIGINAL = "cf_" + "a" * 32
REPLACEMENT = "cf_" + "b" * 32
CROP = "cf_" + "c" * 32
OTHER_STAFF = "cf_" + "d" * 32
SECOND_PHOTO = "cf_" + "e" * 32
SECOND_OTHER = "cf_" + "f" * 32
FEEDBACK_PHOTO = "cf_" + "1" * 32
ACTOR = ActorContext("admin:fixture")


@pytest.fixture
def web_fixture():
    item = WebProfileTemplateItem(42, 1, "健康檢查", WebProfileCategory.OTHER, 20, True)
    photo_item = WebProfileTemplateItem(43, 1, "生活照", WebProfileCategory.PHOTO, 10)
    items = {42: item, 43: photo_item}
    photos, approvals, commits, removals = {}, {}, [], {}
    metadata = {
        ORIGINAL: (7, "staff-web/original"), REPLACEMENT: (7, "staff-web/original"),
        CROP: (7, f"staff-web/crop/{REPLACEMENT}"), OTHER_STAFF: (8, "staff-web/original"),
        SECOND_PHOTO: (7, "staff-web/original"), SECOND_OTHER: (7, "staff-web/original"),
        FEEDBACK_PHOTO: (7, "staff-web/original"),
    }

    @contextmanager
    def uow():
        yield SimpleNamespace(commit=lambda: commits.append(True))

    def publish(staff_id, photo, actor):
        entry_id = photo.entry_id or max((key[1] for key in photos), default=0) + 1
        saved = PublishedWebProfilePhoto(
            entry_id, (photo.entry_version or 0) + 1, staff_id, items[photo.template_item_id],
            photo.original_file_id, photo.crop_file_id, photo.expiry_date,
        )
        photos[staff_id, entry_id] = saved
        return saved

    def save_template(item, actor):
        saved = replace(item, item_id=item.item_id or max(items) + 1, version=item.version + 1)
        items[saved.item_id] = saved
        return saved

    def entry(staff_id, entry_id, **_):
        return None if (staff_id, entry_id) in removals else photos.get((staff_id, entry_id))

    def other_current(staff_id, item_id, **_):
        latest = max(
            (row for row in photos.values() if row.staff_id == staff_id and row.item.item_id == item_id),
            key=lambda row: row.entry_id, default=None,
        )
        return entry(staff_id, latest.entry_id) if latest else None

    def approval(operation, staff_id, *, lock=False, command=None):
        stored = approvals.get((operation, staff_id))
        if stored is None:
            return None
        saved_command, result = stored
        if (lock or command is not None) and command != saved_command:
            raise WebProfileConflict("staff_web_operation_mismatch")
        return result

    def remove(staff_id, item_id, expected, actor):
        removals[staff_id, expected.entry_id] = (item_id, expected.entry_version, actor)

    repo = SimpleNamespace(
        templates=lambda: tuple(items.values()),
        template=lambda item_id, **_: items.get(item_id),
        save_template=save_template,
        staff_name=lambda staff_id, **_: {7: "測試月嫂"}.get(staff_id),
        current=lambda staff_id: tuple(
            row for row in sorted(photos.values(), key=lambda row: row.item.display_order)
            if row.staff_id == staff_id and entry(staff_id, row.entry_id) is not None and (
                row.item.category is not WebProfileCategory.OTHER or row == other_current(staff_id, row.item.item_id)
            )
        ),
        entry=entry,
        other_current=other_current,
        has_multiple_active_entries=lambda item_id: sum(
            row.item.item_id == item_id and entry(row.staff_id, row.entry_id) is not None for row in photos.values()
        ) > 1,
        removed=lambda staff_id, item_id, expected: (
            removals.get((staff_id, expected.entry_id), ())[:2] == (item_id, expected.entry_version)
        ),
        remove=remove,
        original_used=lambda file_id, **_: any(row.original_file_id == file_id for row in photos.values()),
        publish=publish, approval=approval,
        record_approval=lambda operation, staff_id, result, *, command=None: approvals.update({
            (operation, staff_id): (command, result),
        }),
    )
    files = SimpleNamespace(
        download=lambda file_id: file_id,
        readback=lambda file_id: SimpleNamespace(
            owner=ControlledFileOwner.STAFF, purpose=ControlledFilePurpose.STAFF_PROFILE_PHOTO,
            subject_reference=str(metadata[file_id][0]), logical_folder=metadata[file_id][1],
            filename=f"stored-{file_id[-1]}.png",
        ),
    )
    return StaffWebProfile(repo, lambda: files, uow), uow, commits


def test_combined_submission_publishes_only_manually_and_replays(web_fixture):
    web, uow, commits = web_fixture
    profile_writes = []
    profile = SimpleNamespace(
        preview=lambda staff_id, values, version: SimpleNamespace(
            before={"phone": None}, after=values, preview_fingerprint=PreviewFingerprint("a" * 64),
        ),
        apply_in_current_uow=lambda *args: profile_writes.append(args[1]),
    )
    application = StaffProfileChangeApproval(uow, profile, None, None, None, None, web)
    raw = [
        encode_web_photo(WebProfilePhoto(42, ORIGINAL, date(2026, 10, 1), template_version=1)),
        encode_web_photo(WebProfilePhoto(43, REPLACEMENT, template_version=1)),
    ]
    content, review = application.prepare(7, {"profile": {"phone": "0900000000"}, "web_contents": raw}, {"profile": 0})
    assert len(review["web_contents"]) == 2
    assert web.customer_page(7) == {"name": "測試月嫂", "groups": []}
    change = restore_staff_profile_change(7, content)
    operation = uuid4()
    application.apply(change, operation, ACTOR, "")
    assert commits == [True] and profile_writes == [{"phone": "0900000000"}]
    first_page = web.customer_page(7)
    assert first_page == {"name": "測試月嫂", "groups": [
        {"category": "photo", "images": [{"item_name": "生活照", "image_entry": 2, "image_version": 1}]},
        {"category": "other", "images": [{"item_name": "健康檢查", "image_entry": 1, "image_version": 1}]},
    ]}
    # The unchanged published receipt is returned after a late Redis completion retry.
    assert web.apply_in_current_uow(7, change.web_contents, operation, ACTOR) == web.repository.approval(operation, 7)
    assert web.customer_page(7) == first_page


def test_crop_replacement_keeps_published_pointer_until_approval(web_fixture):
    web, _, _ = web_fixture
    original = WebProfilePhoto(42, ORIGINAL, date(2026, 10, 1), template_version=1)
    web.apply_in_current_uow(7, web.prepare(7, [original]), uuid4(), ACTOR)
    replacement = replace(original, original_file_id=REPLACEMENT, entry_id=1, entry_version=1)
    pending, = web.prepare(7, [replacement])
    cropped = replace(pending, crop_file_id=CROP)
    assert web.pending_image(7, cropped, original=True) == REPLACEMENT
    assert web.pending_image(7, cropped, original=False) == CROP
    assert web.customer_image(7, 1, 1) == ORIGINAL
    with pytest.raises(LookupError):
        web.customer_image(7, 1, 2)
    web.apply_in_current_uow(7, [cropped], uuid4(), ACTOR)
    assert web.customer_image(7, 1, 2) == CROP
    with pytest.raises(LookupError):
        web.customer_image(7, 1, 1)
    with pytest.raises(WebProfileConflict, match="publication_stale"):
        web.apply_in_current_uow(7, [cropped], uuid4(), ACTOR)


def test_feedback_stays_private_until_two_photos_are_published_without_expiry(web_fixture) -> None:
    web, _, _ = web_fixture
    feedback = web.save_template(
        WebProfileTemplateItem(None, 0, "客戶反饋", WebProfileCategory.FEEDBACK, 0, True), ACTOR,
    )
    certificate = web.save_template(
        WebProfileTemplateItem(None, 0, "專業證照", WebProfileCategory.CERTIFICATE, 30), ACTOR,
    )
    assert feedback.item_id is not None and certificate.item_id is not None
    expiry = date(2026, 12, 31)
    web.publish_uploaded(7, [
        WebProfilePhoto(42, ORIGINAL, expiry, template_version=1),
        WebProfilePhoto(certificate.item_id, REPLACEMENT, template_version=certificate.version),
        WebProfilePhoto(43, SECOND_PHOTO, template_version=1),
    ], uuid4(), ACTOR)
    assert [group["category"] for group in web.customer_page(7)["groups"]] == ["photo", "certificate", "other"]

    pending = web.prepare(7, [
        WebProfilePhoto(feedback.item_id, SECOND_OTHER, template_version=feedback.version),
        WebProfilePhoto(feedback.item_id, FEEDBACK_PHOTO, template_version=feedback.version),
    ])
    assert [group["category"] for group in web.customer_page(7)["groups"]] == ["photo", "certificate", "other"]

    published = web.publish_uploaded(7, pending, uuid4(), ACTOR)
    groups = web.customer_page(7)["groups"]
    assert [group["category"] for group in groups] == ["photo", "certificate", "other", "feedback"]
    assert groups[-1]["images"] == [
        {"item_name": "客戶反饋", "image_entry": entry.entry_id, "image_version": entry.entry_version}
        for entry in published
    ]
    assert len(groups[-1]["images"]) == 2
    folder = next(folder for folder in web.folders(7) if folder.template_item_id == feedback.item_id)
    assert [file.expiry_date for file in folder.files] == [None, None]
    assert feedback.reminder_enabled is False
    assert not feedback.reminder_due(expiry, date(2026, 12, 1))


def test_reject_foreign_file_missing_date_and_stale_template(web_fixture):
    web, _, _ = web_fixture
    with pytest.raises(ValueError, match="expiry_required"):
        web.prepare(7, [WebProfilePhoto(42, ORIGINAL, template_version=1)])
    with pytest.raises(ValueError, match="file_owner"):
        web.prepare(7, [WebProfilePhoto(43, OTHER_STAFF, template_version=1)])
    with pytest.raises(WebProfileConflict, match="template_stale"):
        web.prepare(7, [WebProfilePhoto(43, ORIGINAL, template_version=2)])
    assert web.customer_page(7)["groups"] == []


def test_upload_rejects_spoofed_mime_and_accepts_image_with_server_detected_type(monkeypatch):
    writes = []

    @contextmanager
    def application():
        yield SimpleNamespace(web_profile=SimpleNamespace(
            upload_original=lambda *args: writes.append(args) or ORIGINAL,
        )), object()

    monkeypatch.setattr(route, "staff_profile_change_application", application)
    monkeypatch.setattr(route, "_bound_staff_id", lambda body: 7)
    monkeypatch.setattr(route, "_require_active", lambda lifecycle, staff_id: None)
    monkeypatch.setattr(route, "file_transfer_settings", lambda: SimpleNamespace(photo_max_bytes=4_100_000))
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as client:
        payload = {"upload_id": str(uuid4())}
        path = "/api/v1/line/staff-self-service/profile-change/photos"
        bad = client.post(path, data=payload, files={"photograph": ("invalid.png", b"bad bytes", "image/png")})
        assert bad.status_code == 422 and not writes
        assert bad.json()["detail"]["error"]["code"] == "staff_web_photo_format_invalid"
        heif = bytes.fromhex("000000186674797068656963000000006d69663168656963")
        unsupported = client.post(path, data=payload, files={"photograph": ("photo.HEIC", heif, "application/octet-stream")})
        assert unsupported.status_code == 422 and not writes
        assert unsupported.json()["detail"]["error"]["code"] == "staff_web_photo_heif_unsupported"
        too_large = client.post(path, data=payload, files={"photograph": ("large.png", b"x" * 4_100_001, "image/png")})
        assert too_large.status_code == 422 and not writes
        assert too_large.json()["detail"]["error"]["code"] == "staff_web_photo_too_large"
        stream = BytesIO()
        width, height = 1250, 1040
        pixels = Random(7).randbytes(width * height * 3)
        Image.frombytes("RGB", (width, height), pixels).save(stream, "PNG", compress_level=0)
        assert 3_900_000 < stream.tell() < 3_910_000
        valid = client.post(path, data=payload, files={"photograph": ("legacy.bin", stream.getvalue(), "text/plain")})
        assert valid.status_code == 200
        assert valid.json()["data"]["file_id"] == ORIGINAL
        assert writes[0][2:4] == ("photo.png", "image/png")
        stream = BytesIO()
        Image.new("RGB", (16, 16)).save(stream, "JPEG")
        jpeg = stream.getvalue()
        comment_size = 64_000
        comment = b"\xff\xfe" + (comment_size + 2).to_bytes(2, "big") + b" " * comment_size
        jpeg = jpeg[:2] + comment * 61 + jpeg[2:]
        assert 3_900_000 < len(jpeg) < 3_910_000
        assert client.post(path, data=payload, files={"photograph": ("photo.jpg", jpeg, "")}).status_code == 200
        assert writes[1][2:4] == ("photo.jpg", "image/jpeg")


def test_other_pending_expectations_and_removal_keep_current_relation_consistent(web_fixture):
    web, _, _ = web_fixture
    date_value = date(2026, 10, 1)
    first = WebProfilePhoto(42, ORIGINAL, date_value, template_version=1)
    opening, = web.prepare(7, [first])
    pending_when_empty, = web.prepare(7, [replace(first, original_file_id=REPLACEMENT)])
    with pytest.raises(ValueError, match="other_single_photo"):
        web.prepare(7, [opening, pending_when_empty])
    with pytest.raises(ValueError, match="other_single_photo"):
        web.apply_in_current_uow(7, [opening, pending_when_empty], uuid4(), ACTOR)
    saved, = web.publish_uploaded(7, [opening], uuid4(), ACTOR)
    with pytest.raises(WebProfileConflict, match="publication_stale"):
        web.apply_in_current_uow(7, [pending_when_empty], uuid4(), ACTOR)
    replacement = replace(pending_when_empty, entry_id=saved.entry_id, entry_version=saved.entry_version)
    pending, = web.prepare(7, [replacement])
    assert web.customer_image(7, saved.entry_id, 1) == ORIGINAL
    operation = uuid4()
    published, = web.publish_uploaded(7, [pending], operation, ACTOR)
    assert published == WebProfileEntryVersion(saved.entry_id, 2)
    assert web.publish_uploaded(7, [pending], operation, ACTOR) == (published,)
    with pytest.raises(WebProfileConflict, match="operation_mismatch"):
        web.publish_uploaded(7, [replace(pending, expiry_date=date(2027, 1, 1))], operation, ACTOR)
    with pytest.raises(WebProfileConflict, match="publication_stale"):
        web.remove_publication(7, 42, 1, saved, ACTOR)
    assert web.customer_image(7, published.entry_id, 2) == REPLACEMENT
    web.remove_publication(7, 42, 1, published, ACTOR)
    web.remove_publication(7, 42, 1, published, ACTOR)
    assert web.customer_page(7)["groups"] == []
    with pytest.raises(LookupError):
        web.customer_image(7, published.entry_id, 2)
    assert all(folder.count == 0 for folder in web.folders(7))
    uploaded_again, = web.publish_uploaded(7, [replace(first, original_file_id=SECOND_OTHER)], uuid4(), ACTOR)
    assert uploaded_again.entry_id != published.entry_id


def test_registry_reader_gets_metadata_and_owner_writer_removes_only_exact_version(monkeypatch, web_fixture):
    web, _, _ = web_fixture
    photo = WebProfilePhoto(42, ORIGINAL, date(2026, 10, 1), template_version=1)
    entry, = web.publish_uploaded(7, [photo], uuid4(), ACTOR)

    @contextmanager
    def application():
        yield web

    monkeypatch.setattr(route, "staff_web_profile_application", application)
    app = FastAPI()
    app.include_router(route.router)
    staff_path = "/api/v1/admin/staff-web-profile/7"
    target = f"{staff_path}/folders/42/entries/{entry.entry_id}"
    versions = {"template_version": 1, "entry_version": entry.entry_version}
    with TestClient(app) as client:
        assert client.get(f"{staff_path}/folders").status_code == 401
        principal = SimpleNamespace(id=7, effective_capabilities=lambda: frozenset({"data_browser.read"}))
        app.dependency_overrides[require_admin] = lambda: principal
        result = client.get(f"{staff_path}/folders")
        assert result.json()["data"] == {"items": [
            {"template_item_id": 42, "template_version": 1, "name": "健康檢查", "category": "other",
             "count": 1, "files": [{"entry_id": entry.entry_id, "entry_version": 1, "filename": "stored-a.png",
                                    "expiry_date": "2026-10-01"}]},
            {"template_item_id": 43, "template_version": 1, "name": "生活照", "category": "photo",
             "count": 0, "files": []},
        ]}
        assert result.headers["Cache-Control"] == "private, no-store"
        assert client.get(f"{staff_path}/website").status_code == 200
        assert client.get(f"{staff_path}/preview").status_code == 403
        assert client.delete(target, params=versions).status_code == 403
        principal.effective_capabilities = lambda: frozenset({"data_browser.read", "data_browser.write"})
        assert client.delete(target.replace("/42/", "/43/"), params=versions).status_code == 409
        assert client.delete(target, params={**versions, "entry_version": 2}).status_code == 409
        assert client.delete(target, params=versions).json()["data"] == {"entry_id": entry.entry_id}
        assert client.get(f"{staff_path}/website").json()["data"]["groups"] == []


def test_template_admin_version_and_current_category_are_shared(monkeypatch, web_fixture):
    web, _, _ = web_fixture

    @contextmanager
    def web_application():
        yield web

    monkeypatch.setattr(route, "staff_web_profile_application", web_application)
    monkeypatch.setattr(route, "admin_actor_context", lambda _: ACTOR)
    app = FastAPI()
    app.include_router(route.router)
    path = "/api/v1/admin/staff-web-profile/templates"
    with TestClient(app) as client:
        assert client.get(path).status_code in {401, 403}
        app.dependency_overrides[route.require_registry_writer] = lambda: object()
        body = {"name": "寶寶按摩證書", "category": "other", "display_order": 2, "reminder_enabled": True}
        created = client.post(path, json=body).json()["data"]
        assert created["reminder_lead"] == {"months": 1, "days": 0}
        changed = client.put(f"{path}/{created['item_id']}", json={
            **body, "category": "certificate", "version": created["version"],
        }).json()["data"]
        assert changed["category"] == "certificate" and changed["reminder_enabled"] is False
        assert client.put(f"{path}/{created['item_id']}", json={**body, "version": created["version"]}).status_code == 409
        assert web.self_service(7)["templates"] == web.self_service(8)["templates"]
        assert web.customer_page(7)["groups"] == []


def test_matching_reader_previews_only_published_web_profile(monkeypatch, web_fixture):
    web, uow, commits = web_fixture
    original = WebProfilePhoto(42, ORIGINAL, date(2026, 10, 1), template_version=1)
    portrait = WebProfilePhoto(43, SECOND_PHOTO, template_version=1)
    web.apply_in_current_uow(7, web.prepare(7, [original, portrait]), uuid4(), ACTOR)
    web.prepare(7, [replace(original, original_file_id=REPLACEMENT, entry_id=1, entry_version=1)])

    def download(file_id):
        color = {ORIGINAL: "red", REPLACEMENT: "blue"}[file_id]
        stream = BytesIO()
        Image.new("RGB", (2, 2), color).save(stream, "PNG")
        return SimpleNamespace(content=stream.getvalue())

    @contextmanager
    def application():
        yield StaffWebProfile(web.repository, lambda: SimpleNamespace(download=download), uow)

    monkeypatch.setattr(route, "staff_web_profile_application", application)
    app = FastAPI()
    app.include_router(route.router)
    page_path = "/api/v1/admin/staff-web-profile/7/preview"
    published_image_path = f"{page_path}/images/1/1"
    pending_image_path = f"{page_path}/images/1/2"
    with TestClient(app) as client:
        for path in (page_path, published_image_path):
            assert client.get(path).status_code == 401

        principal = SimpleNamespace(id=7, effective_capabilities=lambda: frozenset())
        app.dependency_overrides[require_admin] = lambda: principal
        for path in (page_path, published_image_path):
            assert client.get(path).status_code == 403

        principal.effective_capabilities = lambda: frozenset({"line.matching.read"})
        page = client.get(page_path)
        assert page.status_code == 200
        assert page.headers["Cache-Control"] == "private, no-store"
        assert page.json()["data"] == {"name": "測試月嫂", "groups": [
            {"category": "photo", "images": [{"item_name": "生活照", "image_entry": 2, "image_version": 1}]},
            {"category": "other", "images": [{"item_name": "健康檢查", "image_entry": 1, "image_version": 1}]},
        ]}
        image = client.get(published_image_path)
        assert image.status_code == 200
        assert image.headers["Content-Type"] == "image/png"
        assert image.headers["Cache-Control"] == "private, no-store"
        with Image.open(BytesIO(image.content)) as contents:
            assert contents.getpixel((0, 0)) == (255, 0, 0)
        assert client.get(pending_image_path).status_code == 404
        assert client.get(published_image_path.replace("/7/", "/8/")).status_code == 404
    assert commits == []


@pytest.mark.parametrize(("configured_root", "error_code"), [
    (None, "file_settings_unavailable"),
    ("fixture-private/invalid-root", "staff_web_storage_layout_unavailable"),
])
def test_web_profile_image_storage_layout_returns_safe_503(
    monkeypatch, tmp_path, web_fixture, configured_root, error_code,
):
    web, _, _ = web_fixture
    photo = WebProfilePhoto(43, ORIGINAL, template_version=1)
    web.apply_in_current_uow(7, web.prepare(7, [photo]), uuid4(), ACTOR)
    monkeypatch.setenv("APP_ENV", "production")
    if configured_root is None:
        monkeypatch.delenv("CONTROLLED_FILE_STORAGE_ROOT", raising=False)
        monkeypatch.delenv("FILE_SETTINGS_PATH", raising=False)
    else:
        monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", configured_root)
        monkeypatch.setenv("FILE_SETTINGS_PATH", str(tmp_path / "file-settings.json"))

    @contextmanager
    def application():
        service = build_staff_web_profile(object())
        service.repository = web.repository
        yield service

    monkeypatch.setattr(route, "staff_web_profile_application", application)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.require_line_matching_reader] = lambda: object()
    with TestClient(app) as client:
        result = client.get("/api/v1/admin/staff-web-profile/7/preview/images/1/1")
    assert result.status_code == 503
    error = result.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["code"] == error_code
    assert error["message"] == "照片儲存暫時無法使用，請稍後重試。"
    assert "fixture-private" not in result.text
    assert "CONTROLLED_FILE_STORAGE_ROOT" not in result.text


def test_merged_review_with_disposable_redis_crops_rejects_and_reads_publications(monkeypatch, web_fixture):
    test_port = os.getenv("STAFF_PROFILE_CHANGE_TEST_REDIS_PORT")
    if test_port is None:
        pytest.skip("requires a disposable Redis bound to localhost")
    assert int(test_port) != 6379
    web, transaction, commits = web_fixture
    profile_writes = []
    profile = SimpleNamespace(
        preview=lambda _staff, values, _version: SimpleNamespace(
            before={"phone": None}, after=values, preview_fingerprint=PreviewFingerprint("a" * 64),
        ),
        apply_in_current_uow=lambda *args: profile_writes.append(args[1]),
    )
    application = StaffProfileChangeApproval(transaction, profile, None, None, None, None, web)
    lifecycle = SimpleNamespace(load=lambda _staff, **_: SimpleNamespace(state=StaffLifecycleState.ACTIVE))
    stream = BytesIO()
    Image.new("RGB", (4, 4), "red").save(stream, "PNG")
    saved_images = {REPLACEMENT: stream.getvalue()}
    pending_image = web.pending_image
    monkeypatch.setattr(web, "pending_image", lambda staff, photo, **options: SimpleNamespace(
        content=saved_images[pending_image(staff, photo, **options)], content_type="image/png",
    ))

    def save_crop(_staff, original_id, _crop_id, _filename, _mime, data, _actor):
        assert original_id == REPLACEMENT
        saved_images[CROP] = data
        return CROP

    monkeypatch.setattr(web, "save_crop", save_crop)
    monkeypatch.setattr(route, "file_transfer_settings", lambda: SimpleNamespace(photo_max_bytes=4096))
    subject = {"staff_id": 7}

    @contextmanager
    def profile_application():
        yield application, lifecycle

    @contextmanager
    def web_application():
        yield web

    redis = Redis(host="127.0.0.1", port=int(test_port), decode_responses=True, socket_connect_timeout=2)
    staging = StaffProfileChangeStaging(redis)
    monkeypatch.setattr(intake, "staff_profile_change_application", profile_application)
    monkeypatch.setattr(route, "staff_web_profile_application", web_application)
    for module in (intake, route):
        monkeypatch.setattr(module, "staff_profile_change_staging", lambda: staging)
        monkeypatch.setattr(module, "_bound_staff_id", lambda body: subject["staff_id"])
        monkeypatch.setattr(module, "admin_actor_context", lambda _: ACTOR)
    app = FastAPI()
    app.include_router(intake.router)
    app.include_router(route.router)
    path = "/api/v1/line/staff-self-service/profile-change"
    expiry = "2026-12-31"
    submission = {
        "submission_id": str(uuid4()),
        "basis": {"profile": 0, "bank": 0, "relations": "a" * 64, "transportation": "b" * 64, "matching": 0},
        "profile": {"phone": "0900000000"},
        "web_contents": [
            {"template_item_id": 43, "template_version": 1, "original_file_id": REPLACEMENT},
            {"template_item_id": 43, "template_version": 1, "original_file_id": SECOND_PHOTO},
            {"template_item_id": 42, "template_version": 1, "original_file_id": ORIGINAL, "expiry_date": expiry},
            {"template_item_id": 42, "template_version": 1, "original_file_id": SECOND_OTHER, "expiry_date": expiry},
        ],
    }
    try:
        with TestClient(app) as client:
            accepted = client.post(f"{path}/submit", json=submission).json()["data"]
            assert client.post(f"{path}/submit", json=submission).json()["data"] == accepted
            changed = {**submission, "profile": {"phone": "0900000001"}}
            assert client.post(f"{path}/submit", json=changed).status_code == 409
            assert accepted["status"] == "pending" and not commits
            application_id = accepted["id"]
            review = f"/api/v1/admin/staff-profile-change-requests/{application_id}"
            assert client.post(f"{review}/decision", json={"action": "approve", "version": 1}).status_code in {401, 403}
            app.dependency_overrides[route.require_registry_writer] = lambda: object()
            pending = client.get(review).json()["data"]
            assert len(pending["changes"]["web_contents"]) == 4
            assert pending["changes"]["profile"]["after"]["phone"] == "0900000000"
            subject["staff_id"] = 8
            assert client.post(f"{path}/{application_id}/status", json={}).status_code == 404
            subject["staff_id"] = 7
            assert client.post(f"{path}/{application_id}/status", json={}).json()["data"]["status"] == "pending"
            crop = {"version": 1, "crop_id": str(uuid4()), "left": 0, "top": 0, "right": 2, "bottom": 3}
            crop_path = f"{review}/web-photos/0"
            changed = client.put(f"{crop_path}/crop", json=crop).json()["data"]
            assert changed["version"] == 2
            assert changed["changes"]["web_contents"][0]["crop_file_id"] == CROP
            result = client.get(crop_path)
            assert Image.open(BytesIO(result.content)).size == (2, 3)
            assert Image.open(BytesIO(client.get(crop_path, params={"original": True}).content)).size == (4, 4)
            assert client.delete(f"{crop_path}/crop", params={"version": 1}).status_code == 409
            cancelled = client.delete(f"{crop_path}/crop", params={"version": 2}).json()["data"]
            assert cancelled["version"] == 3 and cancelled["changes"]["web_contents"][0]["crop_file_id"] is None
            assert web.customer_page(7)["groups"] == []
            declined = client.post(f"{review}/decision", json={"action": "reject", "version": 3}).json()["data"]
            assert declined["status"] == "rejected" and not commits
            assert web.customer_page(7)["groups"] == []

            new = client.post(f"{path}/submit", json={**submission, "submission_id": str(uuid4())}).json()["data"]
            publish = f"/api/v1/admin/staff-profile-change-requests/{new['id']}/decision"
            decision = {"action": "approve", "version": new["version"]}
            approved = client.post(publish, json=decision).json()["data"]
            assert approved["status"] == "approved" and len(approved["publications"]) == 4
            assert client.post(publish, json=decision).json()["data"] == approved
            assert commits == [True] and profile_writes == [{"phone": "0900000000"}]
            assert [len(group["images"]) for group in web.customer_page(7)["groups"]] == [2, 2]
    finally:
        redis.close()


def test_customer_scope_requires_bound_recipient_and_current_recommended_staff():
    fixture_now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    customer = LineUserId("U-customer")
    interaction = {
        "action_scope": "customer_decision", "interaction_status": "active",
        "expires_at_utc": datetime(2026, 11, 25), "recipient_line_user_id": customer.value,
        "plan_id": 9, "case_no": "synthetic",
    }
    state = SimpleNamespace(plan_is_active=True, customer_line_user_id=customer, segments=[SimpleNamespace(staff_id=7)])
    repository = SimpleNamespace(
        interaction=lambda *_args, **_options: interaction,
        get_contact_state=lambda *_args: state,
        customer_confirmation_snapshot=lambda *_args: {"staff_web_profile_ids": [7]},
    )

    @contextmanager
    def uow():
        yield SimpleNamespace(matching_notifications=repository)

    application = MatchingNotificationApplication(uow, lambda: fixture_now, availability_validator=lambda state: None)
    application.require_customer_web_profile("fixture-token", customer, 7)
    with pytest.raises(LookupError):
        application.require_customer_web_profile("fixture-token", customer, 8)
    with pytest.raises(LookupError):
        application.require_customer_web_profile("fixture-token", LineUserId("U-unbound"), 7)
    interaction["interaction_status"] = "revoked"
    with pytest.raises(LookupError):
        application.require_customer_web_profile("fixture-token", customer, 7)


def test_calendar_month_reminder_queues_once_and_revoked_binding_blocks_delivery(monkeypatch, web_fixture):
    web, _, _ = web_fixture
    assert ReminderLead().starts_on(date(2028, 3, 31)) == date(2028, 2, 29)
    assert ReminderLead(0, 7).starts_on(date(2026, 12, 31)) == date(2026, 12, 24)
    original = WebProfilePhoto(42, ORIGINAL, date(2026, 12, 31), template_version=1)
    web.apply_in_current_uow(7, web.prepare(7, [original]), uuid4(), ACTOR)
    published, = web.repository.current(7)
    without_dates = replace(published.item, category=WebProfileCategory.CERTIFICATE)
    assert not without_dates.reminder_enabled and without_dates.expiry_for_submission(original.expiry_date) is None
    binding = SimpleNamespace(
        line_user_id=LineUserId("U-staff"), version=ExpectedVersion(3), status=LineIdentityBindingStatus.BOUND,
    )
    tasks, receipts = [], {}
    now = datetime(2026, 11, 30, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(reminders, "configured_text", lambda _unit, _template, _default, fields: fields["item_name"])

    def enqueue(request):
        tasks.append(request)
        return SimpleNamespace(task_id=SimpleNamespace(value=5))

    @contextmanager
    def uow():
        yield SimpleNamespace(
            staff_web_profiles=SimpleNamespace(entry=web.repository.entry, reminder_candidates=lambda *_: (published,)),
            identities=SimpleNamespace(get_by_subject=lambda *_: binding),
            staff_lifecycle=SimpleNamespace(load=lambda *_args, **_kwargs: SimpleNamespace(state=StaffLifecycleState.ACTIVE)),
            receipts=SimpleNamespace(get=lambda key, **_: receipts.get(key), append=lambda receipt: receipts.update({receipt.key: receipt})),
            delivery_tasks=SimpleNamespace(exists_for_key=lambda key: False, enqueue=enqueue),
            commit=lambda: None,
        )

    worker = reminders.StaffWebExpiryReminderWorker(uow, lambda: now)
    assert worker.run_once() == 1
    assert worker.run_once() == 0 and len(tasks) == 1
    task = SimpleNamespace(request=tasks[0])
    with uow() as unit:
        assert reminders.staff_web_expiry_delivery_is_current(unit, task, now)
        binding.status = LineIdentityBindingStatus.REVOKED
        assert not reminders.staff_web_expiry_delivery_is_current(unit, task, now)


def test_staff_profile_photo_viewer_supports_mobile_pinch_and_reuses_published_image():
    from pathlib import Path

    playwright_api = pytest.importorskip("playwright.sync_api")
    expect, sync_playwright = playwright_api.expect, playwright_api.sync_playwright

    static = next(parent / "line/static" for parent in Path(__file__).resolve().parents
                  if (parent / "line/static/staff_web_profile.html").is_file())
    thumbnail = BytesIO()
    Image.new("RGB", (1000, 700), "#c76542").save(thumbnail, format="PNG")
    image_calls = []

    def serve(request_route):
        path = request_route.request.url.split("?", 1)[0]
        if path.endswith("/staff_web_profile.html"):
            request_route.fulfill(path=static / "staff_web_profile.html", content_type="text/html")
        elif path.endswith("/static/staff_web_profile.js"):
            request_route.fulfill(path=static / "staff_web_profile.js", content_type="text/javascript")
        elif path.endswith("/website/images/9/2"):
            image_calls.append(path)
            request_route.fulfill(body=thumbnail.getvalue(), content_type="image/png")
        elif path.endswith("/website"):
            request_route.fulfill(json={"data": {"name": "測試月嫂", "groups": [
                {"category": "certificate", "images": [
                    {"item_name": "測試證照", "image_entry": 9, "image_version": 2},
                ]},
            ]}})
        else:
            request_route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.route("https://profile.test/**", serve)
        page.add_init_script("sessionStorage.setItem('union_admin_session_token', 'fixture');")
        page.goto("https://profile.test/staff_web_profile.html?mode=admin&staff_id=7")
        opener = page.get_by_role("button", name="放大履歷圖片")
        opener.click()
        dialog = page.get_by_role("dialog", name="履歷照片大圖")
        large = dialog.locator("img")
        expect(dialog).to_be_visible()
        assert large.get_attribute("src") == opener.locator("img").get_attribute("src")
        page.wait_for_function("document.getElementById('photo-large').naturalWidth > 0")

        client = page.context.new_cdp_session(page)
        client.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [
            {"x": 150, "y": 400, "id": 0}, {"x": 240, "y": 400, "id": 1},
        ]})
        client.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [
            {"x": 70, "y": 400, "id": 0}, {"x": 320, "y": 400, "id": 1},
        ]})
        client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(dialog.get_by_role("button", name="縮小圖片")).to_be_enabled()
        assert large.evaluate("(node) => node.getBoundingClientRect().width > node.clientWidth")
        dialog.get_by_role("button", name="關閉大圖").click()
        expect(dialog).not_to_be_visible()
        opener.click()
        expect(dialog.get_by_role("button", name="縮小圖片")).to_be_disabled()
        assert len(image_calls) == 1
        browser.close()
