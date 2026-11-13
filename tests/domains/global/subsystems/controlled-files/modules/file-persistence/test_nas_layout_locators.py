"""New production locators preserve opaque identities and existing transaction ownership."""
from datetime import date, datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest

from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository, _storage_locator_for
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file import storage_layout as layout
from subsystems.controlled_files.workflow import ControlledFileOwner as Owner, ControlledFilePurpose as Purpose, ControlledFileWorkflow


@pytest.fixture
def production(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("purpose,section", [(Purpose.STAFF_RESUME, "resume"), (Purpose.STAFF_CERTIFICATE, "certificates"), (Purpose.STAFF_HEALTH_EXAM, "health_and_police")])
@pytest.mark.parametrize("app_env", ["production", "development"])
def test_staff_files_finalize_to_named_owner_directory_and_download_by_old_staging_identity(production, monkeypatch, purpose, section, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    storage = FileSystemControlledFileStorage(production)
    content = b"synthetic staff document"
    staged = storage.put_staged(idempotency_key="fixture:staff-file", filename="document.pdf", mime_type="application/pdf", content=content)
    candidate = SimpleNamespace(owner=Owner.STAFF, purpose=purpose, subject_reference="12", object_key="resume",
                                mime_type="application/pdf", sha256_digest=staged.sha256_digest)
    locator = _storage_locator_for(candidate, {"storage_locator": staged.staging_id}, version=3,
                                   staff_record={"id": 12, "union_no": "ST012", "name": "測試月嫂"})
    assert locator.startswith(f"{layout.STAFF_DIRECTORY}/ST012_測試月嫂/{section}/")
    assert "v3_" in locator
    storage.finalize_staged(staged.staging_id, expected_sha256=staged.sha256_digest, object_reference=locator)
    assert (production / locator).read_bytes() == content
    assert not (production / "_staging" / "objects" / "cf" / staged.staging_id / "payload.bin").exists()
    assert all((production / layout.STAFF_DIRECTORY / "ST012_測試月嫂" / name).is_dir() for name in ("resume", "certificates", "health_and_police"))
    readback = SimpleNamespace(sha256_digest=staged.sha256_digest, filename="document.pdf", mime_type="application/pdf")
    reference = SimpleNamespace(staging_id=staged.staging_id, readback=readback)
    repository = SimpleNamespace(get_download_reference=lambda _: reference)
    download = ControlledFileWorkflow(repository, storage, None, None).download("cf_" + "b" * 32)
    assert download.content == content


def test_client_passbook_cover_uses_passbook_directory(production):
    digest = hashlib.sha256(b"fixture passbook").hexdigest()
    candidate = SimpleNamespace(
        owner=Owner.CLIENTS,
        purpose=Purpose.CLIENT_PASSBOOK_COVER,
        subject_reference="42",
        object_key="clients/42/passbook_cover",
        mime_type="image/jpeg",
        sha256_digest=digest,
    )
    locator = _storage_locator_for(candidate, {})
    assert locator == f"{layout.CLIENT_PASSBOOK_DIRECTORY}/42/存摺封面_42_v1_{digest[:6]}.jpg"


def test_contract_pdf_and_menu_have_their_business_directories(production):
    candidate = SimpleNamespace(owner=Owner.CONTRACT_SIGNING, purpose=Purpose.FINAL_SIGNED_CONTRACT, subject_reference="2026-A001",
        object_key="signed-contract:fixture:client_copy:v1", mime_type="application/pdf", sha256_digest="a" * 64)
    assert _storage_locator_for(candidate, {}, version=2) == f"{layout.ORDERS_DIRECTORY}/2026-A001/客戶合約_2026-A001_v2_已簽署_aaaaaa.pdf"
    candidate.owner, candidate.purpose = Owner.LINE_INTEGRATION, Purpose.RICH_MENU_BACKGROUND
    assert _storage_locator_for(candidate, {}).startswith(layout.MEDIA_DIRECTORY + "/rich_menus/")


def test_signed_archive_separates_identical_pdfs_for_distinct_caregiver_slots(production):
    candidate = SimpleNamespace(owner=Owner.CONTRACT_SIGNING, purpose=Purpose.FINAL_SIGNED_CONTRACT,
                                subject_reference="CASE-1", object_key="signed-archive:staff:41",
                                mime_type="application/pdf", sha256_digest="a" * 64)
    first = _storage_locator_for(candidate, {})
    candidate.object_key = "signed-archive:staff:42"
    second = _storage_locator_for(candidate, {})
    assert first != second
    assert "月嫂承攬協議_41" in first and "月嫂承攬協議_42" in second


@pytest.mark.parametrize(("target", "label"), [("client", "客戶合約"), ("staff:42", "月嫂承攬協議")])
def test_returned_contract_on_local_drive_remains_downloadable(production, monkeypatch, target, label):
    monkeypatch.setenv("APP_ENV", "development")
    storage = FileSystemControlledFileStorage(production)
    content = b"synthetic signed PDF"
    staged = storage.put_staged(idempotency_key="fixture:signed", filename="signed.pdf",
                                mime_type="application/pdf", content=content)
    candidate = SimpleNamespace(owner=Owner.CONTRACT_SIGNING, purpose=Purpose.FINAL_SIGNED_CONTRACT,
                                subject_reference="CASE-1", object_key=f"signed-contract:session:{target}:v1",
                                mime_type="application/pdf", sha256_digest=staged.sha256_digest)
    locator = _storage_locator_for(candidate, {"storage_locator": staged.staging_id})
    assert locator.startswith(f"{layout.ORDERS_DIRECTORY}/CASE-1/{label}_")
    storage.finalize_staged(staged.staging_id, expected_sha256=staged.sha256_digest, object_reference=locator)
    assert (production / locator).read_bytes() == content
    readback = SimpleNamespace(sha256_digest=staged.sha256_digest, filename="signed.pdf", mime_type="application/pdf")
    reference = SimpleNamespace(staging_id=staged.staging_id, readback=readback)
    repository = SimpleNamespace(get_download_reference=lambda _: reference)
    assert ControlledFileWorkflow(repository, storage, None, None).download("cf_" + "b" * 32).content == content


@pytest.mark.parametrize("app_env", ["production", "development"])
def test_finalize_intent_uses_existing_queue_and_never_commits_outer_transaction(production, monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    calls = []
    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append((sql, parameters))
    connection = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: pytest.fail("no hidden commit"))
    candidate = SimpleNamespace(owner=Owner.STAFF, purpose=Purpose.STAFF_RESUME,
                                staging_id="cfs_" + "a" * 32, sha256_digest="c" * 64)
    file_id = "cf_" + "b" * 32
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(candidate, file_id, datetime.now(timezone.utc))
    assert len(calls) == 1 and "INSERT INTO controlled_file_finalize_intents" in calls[0][0]
    assert calls[0][1][3:5] == (file_id, candidate.staging_id)


def test_development_files_do_not_gain_new_finalize_jobs(production, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    connection = SimpleNamespace(cursor=lambda: pytest.fail("must not queue old development data"))
    candidate = SimpleNamespace(owner=Owner.CONTRACT_SIGNING, purpose=Purpose.UNSIGNED_CONTRACT)
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(candidate, "unused", datetime.now(timezone.utc))


def test_client_passbook_cover_enqueues_finalize_intent(production, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    calls = []
    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append((sql, parameters))
    connection = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: pytest.fail("no hidden commit"))
    candidate = SimpleNamespace(owner=Owner.CLIENTS, purpose=Purpose.CLIENT_PASSBOOK_COVER,
                                staging_id="cfs_" + "a" * 32, sha256_digest="c" * 64)
    file_id = "cf_" + "b" * 32
    MySqlControlledFileWorkflowRepository(connection)._enqueue_nas_finalize(candidate, file_id, datetime.now(timezone.utc))
    assert len(calls) == 1 and "INSERT INTO controlled_file_finalize_intents" in calls[0][0]


@pytest.mark.parametrize("local_documents_only", [False, True])
def test_new_layout_runner_filters_out_all_existing_legacy_locators(production, local_documents_only):
    from infrastructure.mysql.controlled_file_finalize_worker import MySqlControlledFileFinalizeRunner
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): calls.append((sql, parameters))
        def fetchall(self): return ()
    connection = SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
    result = MySqlControlledFileFinalizeRunner(lambda: connection, object(), "fixture-worker", lambda: datetime.now(timezone.utc),
                                               layout_only=True, local_documents_only=local_documents_only).run_once()
    assert result == 0
    assert "SUBSTRING_INDEX(object.storage_locator" in calls[0][0]
    if local_documents_only:
        assert "(object.owner_type, object.purpose," in calls[0][0]
        assert calls[0][1][1:-1] == (
            "staff", "staff_resume", layout.STAFF_DIRECTORY,
            "staff", "staff_certificate", layout.STAFF_DIRECTORY,
            "staff", "staff_health_exam", layout.STAFF_DIRECTORY,
            "contract_signing", "final_signed_contract", layout.ORDERS_DIRECTORY,
            "clients", "client_passbook_cover", layout.CLIENT_PASSBOOK_DIRECTORY,
        )
    else:
        assert calls[0][1][1:-1] == layout.BUSINESS_DIRECTORIES[:4]
