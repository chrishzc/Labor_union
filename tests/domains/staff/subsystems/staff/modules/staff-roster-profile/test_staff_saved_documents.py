"""Original Staff Profile collection and exact CFS membership; no SQL execution."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.staff import router
from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_profile import get_staff_profile_application
from infrastructure.mysql.staff_profile_query_repository import _saved_document, _saved_document_page, _SAVED_DOCUMENTS_SQL
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository, _staff_saved_document_reference_status
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.profile_query import StaffProfileQueryApplication, StaffSavedDocumentPage, StaffSavedDocumentSourceUnavailable, StaffSavedDocumentCursorInvalid
from subsystems.controlled_files.workflow import ControlledFileReadback, ControlledFileOwner, ControlledFilePurpose, ControlledFileDownloadReference

FILE = "cf_" + "a"*32
SECOND = "cf_" + "b"*32
DIGEST = "c"*64
NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


def facts(file_id=FILE, purpose="staff_certificate"):
    return {"opaque_object_id": file_id, "owner_type": "staff", "subject_reference": "7", "purpose": purpose,
        "filename": "certificate.pdf", "version_number": 2, "content_sha256": DIGEST, "content_type": "application/pdf", "size_bytes": 3}


def profile_row():
    fields = "union_no registered_at identity_card phone tel tel_ext email birthday city zip_code address education emergency_contact_name emergency_contact_phone admin_notes".split()
    return {key: None for key in fields} | {"id": 7, "name": "Synthetic Staff", "staff_profile_version": 1, "bank_accounts_version": 0}


class Port:
    def __init__(self): self.rows, self.calls, self.unavailable = [facts(), facts(SECOND, "staff_health_exam")], [], False
    def fetch(self, identity): return profile_row() if identity == 7 else None
    def fetch_bank_accounts(self, identity): return ()
    def fetch_saved_documents(self, staff_id, *, after, page_size, file_id):
        self.calls.append((staff_id, after, page_size, file_id))
        if self.unavailable: raise StaffSavedDocumentSourceUnavailable("synthetic source unavailable")
        rows = self.rows
        if file_id is not None: rows = [row for row in rows if row["opaque_object_id"] == file_id]
        elif after is not None:
            positions = [index for index, row in enumerate(rows) if row["opaque_object_id"] == after]
            if not positions: raise StaffSavedDocumentCursorInvalid("foreign cursor")
            rows = rows[positions[0]+1:]
        return _saved_document_page(rows[:page_size+1], staff_id, page_size, exact=file_id is not None)


def client(port, principal=None):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: principal or AdminPrincipal(9, "reader", "Reader", "system_admin")
    app.dependency_overrides[get_staff_profile_application] = lambda: StaffProfileQueryApplication(port)
    return TestClient(app)


def test_profile_real_owner_collection_pages_saved_files_without_qualification_claims():
    port = Port(); http = client(port)
    first = http.get("/api/v1/staff/7/profile?documents_page_size=1")
    assert first.status_code == 200
    page = first.json()["data"]["documents"]
    assert page["status"] == "available" and page["next_cursor"] == FILE
    assert page["items"][0]["file_id"] == FILE
    assert set(page["items"][0]) == {"staff_id","file_id","purpose","filename","version","sha256_digest","mime_type","size_bytes"}
    second = http.get(f"/api/v1/staff/7/profile?documents_page_size=1&documents_after={FILE}")
    assert second.json()["data"]["documents"]["items"][0]["file_id"] == SECOND
    assert second.json()["data"]["documents"]["next_cursor"] is None
    assert "qualification" not in second.json()["data"]


def test_empty_unavailable_foreign_cursor_and_source_missing_are_distinct():
    port = Port(); http = client(port)
    port.rows = []
    assert http.get("/api/v1/staff/7/profile").json()["data"]["documents"] == {"status":"available","items":[],"next_cursor":None}
    port.unavailable = True
    assert http.get("/api/v1/staff/7/profile").json()["data"]["documents"]["status"] == "unavailable"
    port.unavailable = False
    assert http.get(f"/api/v1/staff/7/profile?documents_after={SECOND}").status_code == 409
    port.fetch_saved_documents = None
    assert http.get("/api/v1/staff/7/profile").json()["data"]["documents"]["status"] == "unavailable"


def test_original_registry_role_and_existing_persisted_file_permission_are_preserved():
    port = Port()
    assert client(port, AdminPrincipal(8,"other","Other","unknown")).get("/api/v1/staff/7/profile").status_code == 403
    assert port.calls == []
    development = AdminPrincipal(None,"dev","Dev","unknown",capabilities=frozenset({"data_browser.read"}))
    response = client(port, development).get("/api/v1/staff/7/profile")
    assert response.status_code == 200 and response.json()["data"]["documents"]["status"] == "unavailable"
    assert port.calls == []


@pytest.mark.parametrize("field,value", [("owner_type","contract_signing"),("subject_reference","8"),("version_number",0),
    ("content_sha256","not-a-hash"),("filename","private/path.pdf"),("purpose","staff_resume")])
def test_malformed_or_cross_owner_source_does_not_become_empty_success(field, value):
    port = Port(); port.rows = [{**facts(),field:value}]
    assert StaffProfileQueryApplication(port).query_saved_documents(7).status == "unavailable"


def test_projection_exposes_overflow_cursor_and_rejects_excess_or_ambiguous_source():
    rows = [facts(FILE),facts(SECOND)]
    page = _saved_document_page(rows,7,1)
    assert len(page.items)==1 and page.next_cursor==FILE
    with pytest.raises(StaffSavedDocumentSourceUnavailable): _saved_document_page(rows,7,1,exact=True)
    with pytest.raises(StaffSavedDocumentSourceUnavailable): _saved_document_page(rows+[facts("cf_"+"d"*32)],7,1)
    # Static only: current is chosen per logical identity before cursor/LIMIT,
    # and the original committed Apply receipt is an exact object FK.
    assert "receipt.controlled_object_id=object.id" in _SAVED_DOCUMENTS_SQL
    assert "newer.object_key=object.object_key AND newer.version_number>object.version_number" in _SAVED_DOCUMENTS_SQL


def test_exact_membership_does_not_accept_a_truncated_or_more_pages_source():
    port = Port()
    port.fetch_saved_documents = lambda *args, **kwargs: StaffSavedDocumentPage("available", (_saved_document(facts(),7),), FILE)
    assert StaffProfileQueryApplication(port).query_saved_documents(7,file_id=FILE).status == "unavailable"


@pytest.mark.parametrize("purpose", [ControlledFilePurpose.STAFF_CERTIFICATE,ControlledFilePurpose.STAFF_HEALTH_EXAM])
@pytest.mark.parametrize("field,value,expected", [(None,None,"matched"),("version_number",3,"mismatch"),
    ("content_sha256","d"*64,"mismatch"),("subject_reference","8","unavailable")])
def test_maintenance_reuses_actual_profile_collection_membership_without_outbound_exemption(monkeypatch,purpose,field,value,expected):
    from infrastructure.mysql import staff_profile_query_repository as source
    port = Port(); port.rows=[facts(purpose=purpose.value)]
    if field: port.rows[0][field]=value
    class Connection:
        def cursor(self): raise AssertionError("project SQL forbidden")
    connection=Connection()
    def factory(actual):
        assert actual is connection
        return port
    monkeypatch.setattr(source,"MySqlStaffProfileQueryRepository",factory)
    actual=MySqlControlledFileWorkflowRepository(connection)
    readback=ControlledFileReadback(FILE,ControlledFileOwner.STAFF,purpose,"7","certificate.pdf","staff/7",2,DIGEST,"application/pdf",3,"registered",NOW)
    actual.get_download_reference=lambda _:ControlledFileDownloadReference(readback,"cfs_"+"a"*32)
    result=actual.reconciliation_reference_status(FILE)
    assert result=={"business_reference":expected,"outbound_reference":"unavailable"}
    assert port.calls[-1][-1]==FILE
    port.unavailable=True
    assert actual.reconciliation_reference_status(FILE)["business_reference"]=="unavailable"
