"""New production locators preserve opaque identities and existing transaction ownership."""
from datetime import date, datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest

from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository, _storage_locator_for
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file import storage_layout as layout
from subsystems.controlled_files.workflow import ControlledFileOwner as Owner, ControlledFilePurpose as Purpose


@pytest.fixture
def production(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("purpose,section", [(Purpose.STAFF_RESUME, "resume"), (Purpose.STAFF_CERTIFICATE, "certificates"), (Purpose.STAFF_HEALTH_EXAM, "health_and_police")])
def test_staff_files_finalize_to_named_owner_directory_and_download_by_old_staging_identity(production, purpose, section):
    storage = FileSystemControlledFileStorage(production)
    content = b"synthetic staff document"
    staged = storage.put_staged(idempotency_key="fixture:staff-file", filename="document.pdf", mime_type="application/pdf", content=content)
    candidate = SimpleNamespace(owner=Owner.STAFF, purpose=purpose, subject_reference="12", object_key="resume",
                                mime_type="application/pdf", sha256_digest=staged.sha256_digest)
    locator = _storage_locator_for(candidate, {}, version=3, staff_record={"id": 12, "union_no": "ST012", "name": "測試月嫂"})
    assert locator.startswith(f"{layout.STAFF_DIRECTORY}/ST012_測試月嫂/{section}/")
    assert "v3_" in locator
    storage.finalize_staged(staged.staging_id, expected_sha256=staged.sha256_digest, object_reference=locator)
    assert (production / locator).read_bytes() == content
    assert all((production / layout.STAFF_DIRECTORY / "ST012_測試月嫂" / name).is_dir() for name in ("resume", "certificates", "health_and_police"))
    assert storage.read_registered_staged(staged.staging_id, expected_sha256=staged.sha256_digest).content == content


@pytest.mark.parametrize("purpose,kind,label", [(Purpose.BABY_LOG_PHOTO, "baby_log_photo", "寶寶"), (Purpose.MEAL_PHOTO, "meal_photo", "餐點")])
def test_care_media_keeps_scheduling_key_and_uses_case_date_directory(production, purpose, kind, label):
    digest = hashlib.sha256(b"fixture photo").hexdigest()
    key = canonical_scheduling_object_key(case_no="2026-A001", service_date=date(2026, 10, 30), attachment_kind=kind, sequence=2, sha256_digest=digest)
    candidate = SimpleNamespace(owner=Owner.SCHEDULING, purpose=purpose, subject_reference="2026-A001", object_key=key,
                                mime_type="image/jpeg", sha256_digest=digest)
    locator = _storage_locator_for(candidate, {})
    assert locator == f"{layout.SCHEDULING_DIRECTORY}/2026-A001/2026-10-30/照護照片_2026-10-30_{label}_2_{digest[:6]}.jpg"
    assert candidate.object_key == key


def test_contract_pdf_and_menu_have_their_business_directories(production):
    candidate = SimpleNamespace(owner=Owner.CONTRACT_SIGNING, purpose=Purpose.FINAL_SIGNED_CONTRACT, subject_reference="2026-A001",
        object_key="signed-contract:fixture:client_copy:v1", mime_type="application/pdf", sha256_digest="a" * 64)
    assert _storage_locator_for(candidate, {}, version=2) == f"{layout.ORDERS_DIRECTORY}/2026-A001/客戶合約_2026-A001_v2_已簽署_aaaaaa.pdf"
    candidate.owner, candidate.purpose = Owner.LINE_INTEGRATION, Purpose.RICH_MENU_BACKGROUND
    assert _storage_locator_for(candidate, {}).startswith(layout.MEDIA_DIRECTORY + "/rich_menus/")


def test_finalize_intent_uses_existing_queue_and_never_commits_outer_transaction(production):
    calls = []
    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append((sql, parameters))
    connection = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: pytest.fail("no hidden commit"))
    candidate = SimpleNamespace(owner=Owner.STAFF, staging_id="cfs_" + "a" * 32, sha256_digest="c" * 64)
    file_id = "cf_" + "b" * 32
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(candidate, file_id, datetime.now(timezone.utc))
    assert len(calls) == 1 and "INSERT INTO controlled_file_finalize_intents" in calls[0][0]
    assert calls[0][1][3:5] == (file_id, candidate.staging_id)


def test_development_files_do_not_gain_new_finalize_jobs(production, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    connection = SimpleNamespace(cursor=lambda: pytest.fail("must not queue old development data"))
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(object(), "unused", datetime.now(timezone.utc))


def test_scheduling_keeps_its_existing_attachment_owned_finalize_intent(production):
    connection = SimpleNamespace(cursor=lambda: pytest.fail("Scheduling already owns its finalize queue write"))
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(SimpleNamespace(owner=Owner.SCHEDULING, purpose=Purpose.BABY_LOG_PHOTO), "unused", datetime.now(timezone.utc))


def test_new_layout_runner_filters_out_all_existing_legacy_locators(production):
    from infrastructure.mysql.controlled_file_finalize_worker import MySqlControlledFileFinalizeRunner
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append((sql, parameters))
        def fetchall(self): return ()
    connection = SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
    result = MySqlControlledFileFinalizeRunner(lambda: connection, object(), "fixture-worker", lambda: datetime.now(timezone.utc), layout_only=True).run_once()
    assert result == 0
    assert "SUBSTRING_INDEX(object.storage_locator" in calls[0][0]
    assert calls[0][1][1:5] == layout.BUSINESS_DIRECTORIES[:4]
