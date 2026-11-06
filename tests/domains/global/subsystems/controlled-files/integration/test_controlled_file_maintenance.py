"""Declared maintenance consumer, original workflow and fresh guards without SQL."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_persisted_admin
from api.dependencies.controlled_files import get_controlled_file_maintenance
from api.routes.controlled_file_maintenance import router
from infrastructure.db.controlled_file_repository import _gc_candidate, _require_cleanup_safe, _contract_reference_status, _staff_resume_reference_status, _GC_CANDIDATES_SQL, MySqlControlledFileWorkflowRepository
from infrastructure.db.contract_external_signing_repository import _final_contract_file_reference
from domains.contract_signing.external_signing import SignedContractDocumentTarget
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.cleanup import CleanupControlledFileStaging, ControlledFileCleanupError, ControlledFileCleanupTerminal, StoredControlledFileCleanup
from subsystems.controlled_files.contracts import ControlledFileStagingCleanupReason, ControlledFileStorageReadiness, ControlledFileStorageStatus, ControlledFileStagingContent
from subsystems.controlled_files.maintenance import ControlledFileMaintenanceApplication
from subsystems.controlled_files.workflow import ControlledFileDownloadReference, ControlledFileReadback, ControlledFileOwner, ControlledFilePurpose
from subsystems.contract_signing.final_document_workflow import FinalContractFileReference
from infrastructure.mysql.service_day_log_photo_reference_repository import _submitted_photo_reference
from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from infrastructure.db.controlled_file_repository import _scheduling_photo_reference_status

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
STAGE = "cfs_" + "a" * 32
FILE = "cf_" + "b" * 32
DIGEST = "c" * 64


def facts():
    return {"id": 1, "staging_id": STAGE, "staging_version": 1, "content_sha256": DIGEST,
            "staging_state": "staged", "created_at_utc": NOW-timedelta(days=3),
            "expires_at_utc": NOW-timedelta(days=2), "object_count": 0, "active_lease_count": 0}


def command():
    return CleanupControlledFileStaging(STAGE, ControlledFileStagingCleanupReason.EXPIRED,
        ExpectedVersion(1), DIGEST, IdempotencyKey("cleanup-test"), ActorContext("admin:7"), CorrelationId("maintenance-test"))


@pytest.mark.parametrize("field,value,code", [
    ("object_count", 1, "controlled_file_cleanup_referenced"),
    ("active_lease_count", 1, "controlled_file_cleanup_leased"),
    ("staging_state", "applied", "controlled_file_cleanup_referenced"),
    ("staging_state", "quarantined", "controlled_file_cleanup_referenced"),
    ("staging_version", 2, "controlled_file_cleanup_staging_conflict"),
    ("content_sha256", "d"*64, "controlled_file_cleanup_staging_conflict"),
    ("created_at_utc", NOW-timedelta(minutes=29), "controlled_file_cleanup_minimum_age"),
    ("expires_at_utc", NOW+timedelta(seconds=1), "controlled_file_cleanup_not_expired"),
])
def test_current_guard_rejects_references_leases_registration_age_and_drift(field, value, code):
    row = facts(); row[field] = value
    with pytest.raises(ControlledFileCleanupError) as caught:
        _require_cleanup_safe(row, command(), NOW)
    assert caught.value.code == code


def test_expired_unregistered_candidate_has_complete_authoritative_projection():
    row = facts()
    candidate = _gc_candidate(row)
    assert candidate.reference_count == 0 and not candidate.active_lease
    _require_cleanup_safe(row, command(), NOW)
    protected = _gc_candidate({**row, "object_count": 1})
    assert protected.registration_status.value == "registered"


def test_candidate_query_bounds_expired_old_unregistered_unleased_rows_before_limit():
    # Static SQL contract only: the user forbids executing even fake-cursor SQL.
    # These predicates precede LIMIT, so protected rows cannot consume its slots.
    query = _GC_CANDIDATES_SQL
    assert "staging.staging_state='staged'" in query
    assert "staging.created_at_utc<=%s AND staging.expires_at_utc<=%s" in query
    assert "NOT EXISTS (SELECT 1 FROM controlled_file_objects registered WHERE registered.source_staging_id=staging.id)" in query
    assert "NOT EXISTS (SELECT 1 FROM controlled_file_leases active WHERE active.staging_object_id=staging.id" in query
    assert "active.lease_state='active' AND active.expires_at_utc>%s)" in query
    assert query.endswith("ORDER BY staging.expires_at_utc,staging.id LIMIT %s")
    assert query.count("%s") == 5


class Connection:
    def __init__(self, events): self.events = events
    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")
    def close(self): self.events.append("close")
    def cursor(self): raise AssertionError("project SQL is forbidden")


class Repository:
    def __init__(self, events):
        self.events, self.row, self.stored = events, facts(), None
        self.observations = []
        self.readback = ControlledFileReadback(FILE, ControlledFileOwner.SCHEDULING, ControlledFilePurpose.MEAL_PHOTO,
            "CASE", "photo.jpg", "photos", 1, DIGEST, "image/jpeg", 3, "registered", NOW)
    def list_staging_gc_candidates(self, **_kwargs): return (_gc_candidate(self.row),)
    def load_cleanup(self, _key, *, for_update): return self.stored
    def begin_cleanup(self, actual, *, cleanup_id, command_fingerprint, occurred_at):
        assert actual.actor.actor_id == "admin:7"
        _require_cleanup_safe(self.row, actual, occurred_at)
        self.events.append("intent")
        self.stored = StoredControlledFileCleanup(cleanup_id, command_fingerprint,
            ControlledFileCleanupTerminal.INTENT, STAGE, actual.reason, actual.expected_staging_version, DIGEST)
        return self.stored
    def complete_cleanup(self, stored, receipt, **_kwargs):
        self.events.append("terminal")
        self.stored = replace(stored, terminal=ControlledFileCleanupTerminal.COMPLETED, receipt=receipt)
    def fail_cleanup(self, *_args, **_kwargs): raise AssertionError("unexpected storage failure")
    def get_download_reference(self, _file_id): return ControlledFileDownloadReference(self.readback, STAGE)
    def append_reconciliation_event(self, event): self.observations.append(event)
    def reconciliation_reference_status(self, _file):
        return {"business_reference": "matched", "outbound_reference": "unavailable"}
    def list_readbacks(self, *, limit):
        assert 1 <= limit <= 100
        return (self.readback,)


class Storage:
    def __init__(self, events): self.events = events
    def cleanup_staged(self, staging_id, **kwargs):
        assert staging_id == STAGE and kwargs["expected_sha256"] == DIGEST
        self.events.append("bytes")
        return True
    def readiness(self): return ControlledFileStorageReadiness(ControlledFileStorageStatus.READY, "ready")
    def read_registered_staged(self, staging_id, **kwargs):
        return ControlledFileStagingContent(staging_id, b"abc", DIGEST, NOW)


def application():
    events = []
    connection = Connection(events)
    repository = Repository(events)
    app = ControlledFileMaintenanceApplication(repository, Storage(events), lambda: MySqlUnitOfWork(connection), FixedBusinessClock(NOW))
    return app, repository, events


def test_formal_preview_then_cleanup_uses_original_three_phase_workflow_and_receipt_replay():
    app, repository, events = application()
    plan = app.preview_cleanup(actor=command().actor, correlation_id=command().correlation_id)
    assert plan["eligible"] == 1 and events == []
    result = app.cleanup(command())
    assert events == ["begin", "intent", "commit", "bytes", "begin", "terminal", "commit"]
    assert result["deleted_set"] == [STAGE] and result["readiness"]["status"] == "ready"
    replay = app.cleanup(command())
    assert replay["receipt"]["cleanup_id"] == result["receipt"]["cleanup_id"]
    assert events.count("bytes") == 1


def test_lease_arriving_after_preview_is_rejected_before_intent_or_bytes():
    app, repository, events = application()
    app.preview_cleanup(actor=command().actor, correlation_id=command().correlation_id)
    repository.row["active_lease_count"] = 1
    with pytest.raises(ControlledFileCleanupError, match="有效租約"):
        app.cleanup(command())
    assert events == ["begin", "rollback"] and repository.stored is None


def test_reconciliation_preview_zero_writes_and_apply_does_not_claim_missing_outbound_evidence():
    app, repository, events = application()
    preview = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert preview["storage_outcome"] == "exact" and not preview["complete"]
    assert preview["status"] == "review_required" and events == [] and repository.observations == []
    result = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id, apply=True)
    assert result["complete"] is False and events == ["begin", "commit"]
    assert len(repository.observations) == 1


@pytest.mark.parametrize("field,value,complete", [
    (None, None, True), ("sha256_digest", "d"*64, False), ("case_no", "OTHER", False),
    ("file_version", 2, False), ("current", False, False), ("completion_receipt_present", False, False),
])
def test_original_contract_frozen_reference_needs_exact_current_file_digest_version_and_receipt(field, value, complete):
    app, repository, _ = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT, mime_type="application/pdf", filename="signed-contract.pdf")
    reference = FinalContractFileReference(FILE, "CASE", DIGEST, 3, True, True, 1, filename="signed-contract.pdf")
    if field is not None: reference = replace(reference, **{field: value})
    repository.reconciliation_reference_status = lambda _: _contract_reference_status(repository.readback, reference)
    result = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert (result["references"]["frozen_completion_reference"] == "matched") is complete
    assert result["references"]["external_completion_reference"] == ("matched" if complete else "unavailable")
    assert result["references"]["outbound_reference"] == "not_applicable" and result["complete"] is complete


@pytest.mark.parametrize("purpose", [ControlledFilePurpose.FINAL_SIGNED_CONTRACT, ControlledFilePurpose.SIGNED_STAFF_AGREEMENT])
@pytest.mark.parametrize("readback_name,member_name,completion,complete", [
    ("signed.pdf", "signed.pdf", "matched", True),
    ("TEST-ONLY-signed.pdf", "TEST-ONLY-signed.pdf", "test_only", False),
    ("TEST-ONLY-signed.pdf", "signed.pdf", "test_only", False),
    ("signed.pdf", "TEST-ONLY-signed.pdf", "test_only", False),
    ("signed.pdf", None, "unavailable", False),
    ("signed.pdf", "other.pdf", "unavailable", False),
])
def test_contract_external_completion_needs_bound_real_member_and_keeps_test_freeze(purpose, readback_name, member_name, completion, complete):
    service, repository, events = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=purpose, mime_type="application/pdf", filename=readback_name)
    reference = FinalContractFileReference(FILE, "CASE", DIGEST, 3, True, True, 1, purpose=purpose, filename=member_name)
    repository.reconciliation_reference_status = lambda _: _contract_reference_status(repository.readback, reference)
    result = service.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["references"] == {"business_reference": "matched", "frozen_completion_reference": "matched",
        "external_completion_reference": completion, "outbound_reference": "not_applicable"}
    assert result["complete"] is complete and events == []


@pytest.mark.parametrize("purpose", [ControlledFilePurpose.FINAL_SIGNED_CONTRACT, ControlledFilePurpose.SIGNED_STAFF_AGREEMENT])
def test_missing_contract_owner_proof_cannot_be_replaced_by_normal_filename(purpose):
    service, repository, events = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=purpose, mime_type="application/pdf", filename="ordinary-signed.pdf")
    repository.reconciliation_reference_status = lambda _: _contract_reference_status(repository.readback, None)
    result = service.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert not result["complete"] and result["references"]["external_completion_reference"] == "unavailable"
    assert events == []


@pytest.mark.parametrize("purpose", [ControlledFilePurpose.FINAL_SIGNED_CONTRACT, ControlledFilePurpose.SIGNED_STAFF_AGREEMENT])
@pytest.mark.parametrize("test_only", [False, True])
def test_real_closed_contract_receipt_projection_supplies_completion_and_test_only_provenance(purpose, test_only):
    from domains.contract_signing.external_signing import ExternalSigningState
    from subsystems.contract_signing.final_document_workflow import (
        FinalContractDocumentReadback, FinalSignedContractApplyReceipt, SignedContractDocumentReadback, signed_contract_object_key,
    )
    from infrastructure.db.contract_external_signing_repository import _final_receipt_snapshot, _final_contract_reference_members
    service, repository, events = application()
    client_target = SignedContractDocumentTarget("client", None, 7)
    staff_target = SignedContractDocumentTarget("staff", 3, 8)
    client_id = FILE if purpose is ControlledFilePurpose.FINAL_SIGNED_CONTRACT else "cf_" + "d"*32
    staff_id = FILE if purpose is ControlledFilePurpose.SIGNED_STAFF_AGREEMENT else "cf_" + "e"*32
    prefix = "TEST-ONLY-" if test_only else ""
    client = SignedContractDocumentReadback(client_target, client_id, 1, prefix + "client.pdf", "application/pdf", 3,
        DIGEST, ControlledFilePurpose.FINAL_SIGNED_CONTRACT)
    staff = SignedContractDocumentReadback(staff_target, staff_id, 1, prefix + "staff.pdf", "application/pdf", 3,
        DIGEST, ControlledFilePurpose.SIGNED_STAFF_AGREEMENT)
    selected = client if purpose is ControlledFilePurpose.FINAL_SIGNED_CONTRACT else staff
    document = FinalContractDocumentReadback("cfd_" + "f"*32, "CASE", client_id, 1, client.filename,
        "application/pdf", 3, "completed", NOW)
    receipt = FinalSignedContractApplyReceipt("cesr_" + "a"*32, "ces_" + "b"*32, 4,
        ExternalSigningState.COMPLETED, document, "contract-identity", (client, staff))
    row = {"object_id": 1 if selected is client else 2, "opaque_object_id": FILE,
        "object_key": signed_contract_object_key(receipt.session_id, selected.target), "owner_type": "contract_signing",
        "purpose": purpose.value, "subject_reference": "CASE", "case_no": "CASE", "external_signing_session_id": receipt.session_id,
        "version_number": 1, "filename": selected.filename, "content_type": "application/pdf", "content_sha256": DIGEST,
        "size_bytes": 3, "is_current": 1, "primary_object_id": 1, "primary_content_sha256": DIGEST, "primary_size_bytes": 3,
        "receipt_id": receipt.receipt_id, "result_status_version": 4, "final_document_id": document.final_document_id,
        "result_snapshot": _final_receipt_snapshot(receipt)}
    reference = _final_contract_file_reference(row, _final_contract_reference_members(row))
    assert reference is not None and reference.filename == selected.filename
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.CONTRACT_SIGNING, purpose=purpose,
        mime_type="application/pdf", filename=selected.filename)
    repository.reconciliation_reference_status = lambda _: _contract_reference_status(repository.readback, reference)
    result = service.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["references"]["frozen_completion_reference"] == "matched"
    assert result["references"]["external_completion_reference"] == ("test_only" if test_only else "matched")
    assert result["complete"] is not test_only and events == []
    if purpose is ControlledFilePurpose.SIGNED_STAFF_AGREEMENT:
        # Historical non-primary members have no independent hash. The client
        # root FK must never supply one for this staff document.
        legacy_staff = replace(staff, sha256_digest=None, purpose=None)
        assert _final_contract_file_reference(row, (client, legacy_staff)) is None


@pytest.mark.parametrize("field,value,matched", [
    (None, None, True), ("file_id", "cf_" + "d"*32, False), ("size_bytes", 4, False),
    ("mime_type", "image/png", False), ("target", SignedContractDocumentTarget("client", None, 8), False),
])
def test_contract_owner_projection_binds_receipt_member_to_size_mime_and_registered_target(field, value, matched):
    target = SignedContractDocumentTarget("client", None, 7)
    row = {"opaque_object_id": FILE, "object_key": "signed-contract:SESSION:client:v7",
        "external_signing_session_id": "SESSION", "case_no": "CASE", "content_sha256": DIGEST,
        "size_bytes": 3, "is_current": 1, "owner_type": "contract_signing", "purpose": "final_signed_contract",
        "subject_reference": "CASE", "version_number": 1, "filename": "contract.pdf", "content_type": "application/pdf",
        "object_id": 1, "primary_object_id": 1, "primary_content_sha256": DIGEST, "primary_size_bytes": 3}
    values = dict(file_id=FILE, version=1, size_bytes=3, mime_type="application/pdf", target=target,
        filename="contract.pdf", sha256_digest=None, purpose=None)
    if field is not None: values[field] = value
    projected = _final_contract_file_reference(row, (SimpleNamespace(**values),))
    assert (projected is not None) is matched
    if matched:
        assert projected.completion_receipt_present and projected.file_version == 1


@pytest.mark.parametrize("references,complete", [
    ({}, False), ({"business_reference": "matched"}, False), ({"outbound_reference": "matched"}, False),
    ({"business_reference": "matched", "outbound_reference": "matched"}, True),
    ({"business_reference": "matched", "outbound_reference": "matched", "frozen_completion_reference": "unavailable"}, False),
])
def test_complete_requires_every_required_world_and_does_not_ignore_owner_freeze(references, complete):
    app, repository, events = application()
    repository.reconciliation_reference_status = lambda _: references
    result = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["complete"] is complete
    assert events == []


@pytest.mark.parametrize("field,value,matched", [
    (None, None, True), ("file_id", "cf_" + "d"*32, False), ("version", 2, False),
    ("sha256_digest", "d"*64, False), ("subject_reference", "8", False),
    ("purpose", ControlledFilePurpose.STAFF_CERTIFICATE, False),
])
def test_staff_resume_reference_is_exact_original_page_file_not_name(field, value, matched):
    app, repository, _ = application()
    target = replace(repository.readback, owner=ControlledFileOwner.STAFF, purpose=ControlledFilePurpose.STAFF_RESUME,
        subject_reference="7", mime_type="application/pdf")
    current = target if field is None else replace(target, **{field: value})
    result = _staff_resume_reference_status(target, current)
    assert (result["business_reference"] == "matched") is matched
    assert result["outbound_reference"] == "not_applicable"


@pytest.mark.parametrize("field,value,complete", [
    (None, None, True), ("file_id", "cf_" + "d"*32, False), ("version", 2, False),
    ("sha256_digest", "d"*64, False), ("size_bytes", 4, False), ("subject_reference", "8", False),
    ("mime_type", "image/jpeg", False), ("missing", None, False),
])
def test_internal_staff_resume_reconciliation_completes_only_exact_page_and_storage_facts(field, value, complete):
    service, repository, events = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.STAFF,
        purpose=ControlledFilePurpose.STAFF_RESUME, subject_reference="7", mime_type="application/pdf")
    current = repository.readback if field is None else (None if field == "missing" else replace(repository.readback, **{field: value}))
    repository.reconciliation_reference_status = lambda _: _staff_resume_reference_status(repository.readback, current)
    result = service.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["complete"] is complete and result["storage_outcome"] == "exact"
    assert result["references"]["outbound_reference"] == "not_applicable" and events == []


@pytest.mark.parametrize("owner,purpose", [
    (ControlledFileOwner.STAFF, ControlledFilePurpose.STAFF_CERTIFICATE),
    (ControlledFileOwner.STAFF, ControlledFilePurpose.STAFF_HEALTH_EXAM),
    (ControlledFileOwner.CONTRACT_SIGNING, ControlledFilePurpose.FINAL_SIGNED_CONTRACT),
    (ControlledFileOwner.LINE_INTEGRATION, ControlledFilePurpose.RICH_MENU_BACKGROUND),
])
def test_resume_offline_exemption_never_applies_to_another_consumer(owner, purpose):
    _, repository, _ = application()
    target = replace(repository.readback, owner=owner, purpose=purpose, mime_type="application/pdf")
    references = _staff_resume_reference_status(target, target)
    assert references == {"business_reference": "mismatch", "outbound_reference": "unavailable"}


@pytest.mark.parametrize("field,value", [("size_bytes", 4), ("sha256_digest", "d"*64)])
def test_resume_offline_exemption_never_bypasses_storage_integrity(field, value):
    service, repository, events = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.STAFF,
        purpose=ControlledFilePurpose.STAFF_RESUME, subject_reference="7", mime_type="application/pdf", **{field: value})
    repository.reconciliation_reference_status = lambda _: _staff_resume_reference_status(repository.readback, repository.readback)
    result = service.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["references"] == {"business_reference": "matched", "outbound_reference": "not_applicable"}
    assert not result["complete"] and result["storage_outcome"] == "digest_mismatch" and events == []


def test_staff_resume_actual_owner_composition_uses_same_existing_page_query_without_sql(monkeypatch):
    from infrastructure.mysql import staff_profile_query_repository as staff_repository
    app, repository, _ = application()
    target = replace(repository.readback, owner=ControlledFileOwner.STAFF, purpose=ControlledFilePurpose.STAFF_RESUME,
        subject_reference="7", mime_type="application/pdf")
    connection = Connection([])
    fields = "union_no registered_at identity_card phone tel tel_ext email birthday city zip_code address education emergency_contact_name emergency_contact_phone admin_notes".split()
    row = {key: None for key in fields} | {"id": 7, "name": "Synthetic Staff", "staff_profile_version": 1, "bank_accounts_version": 0}
    profile_port = SimpleNamespace(fetch=lambda identity: row if identity == 7 else None, fetch_bank_accounts=lambda _: ())
    def profile_factory(actual):
        assert actual is connection
        return profile_port
    monkeypatch.setattr(staff_repository, "MySqlStaffProfileQueryRepository", profile_factory)
    actual = MySqlControlledFileWorkflowRepository(connection)
    actual.get_download_reference = lambda _: ControlledFileDownloadReference(target, STAGE)
    calls = []
    def current(owner, purpose, subject, key):
        calls.append((owner, purpose, subject, key))
        return target
    actual.find_current_readback = current
    assert actual.reconciliation_reference_status(FILE)["business_reference"] == "matched"
    assert calls == [(ControlledFileOwner.STAFF, ControlledFilePurpose.STAFF_RESUME, "7", "resume")]


def test_malformed_real_contract_owner_receipt_stays_review_required_in_http_preview(monkeypatch):
    from infrastructure.db import contract_external_signing_repository as owner
    app, repository, events = application()
    repository.readback = replace(repository.readback, owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT, mime_type="application/pdf")
    actual = MySqlControlledFileWorkflowRepository(Connection(events))
    actual.get_download_reference = repository.get_download_reference
    monkeypatch.setattr(owner.MySqlContractExternalSigningRepository, "get_controlled_file_reference",
        lambda self, _: owner._final_contract_reference_members({"result_snapshot": {}}))
    repository.reconciliation_reference_status = actual.reconciliation_reference_status
    http = FastAPI(); http.include_router(router)
    http.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(id=7, is_root=True, effective_capabilities=lambda: ())
    http.dependency_overrides[get_controlled_file_maintenance] = lambda: app
    response = TestClient(http).post("/api/v1/data-center/reconciliation/preview", json={"file_id": FILE})
    assert response.status_code == 200 and response.json()["data"]["status"] == "review_required"
    assert response.json()["data"]["references"]["business_reference"] == "unavailable"
    assert events == [] and repository.observations == []


@pytest.mark.parametrize("purpose,key,signed", [
    (ControlledFilePurpose.FINAL_SIGNED_CONTRACT, "signed-contract:session:client:v7", True),
    (ControlledFilePurpose.SIGNED_STAFF_AGREEMENT, "signed-contract:session:staff:3:v8", True),
    (ControlledFilePurpose.UNSIGNED_CONTRACT, "historical-client", False),
])
def test_original_contract_locator_labels_both_formal_signed_purposes(monkeypatch, purpose, key, signed):
    from infrastructure.db import controlled_file_repository as source
    monkeypatch.setattr(source, "unified_storage_enabled", lambda: True)
    candidate = SimpleNamespace(owner=ControlledFileOwner.CONTRACT_SIGNING, purpose=purpose,
        subject_reference="CASE", object_key=key, sha256_digest=DIGEST, mime_type="application/pdf")
    locator = source._storage_locator_for(candidate, {"storage_locator": "historical"})
    assert ("_已簽署_" in locator) is signed
    assert ("_未簽署_" in locator) is not signed


def submitted_photo_row(kind):
    # This is the original submitted owner's closed projection. Its original
    # content_fingerprint is format-checked, never recomputed as a new receipt.
    day = NOW.date()
    key = canonical_scheduling_object_key(case_no="CASE",service_date=day,attachment_kind=kind,sequence=1,sha256_digest=DIGEST)
    return {"file_id":FILE,"version":1,"sha256_digest":DIGEST,"size_bytes":3,"mime_type":"image/jpeg",
        "case_no":"CASE","attachment_kind":kind,"log_id":9,"attachment_id":10,"assignment_id":11,"staff_id":7,"event_id":12,
        "service_date":day,"staff_line_user_id":"U-synthetic","content_fingerprint":"f"*64,"idempotency_key":"log-key",
        "event_idempotency_key":"log-key","event_type":"submitted","event_assignment_id":11,"event_staff_id":7,
        "event_service_date":day,"assignment_case_no":"CASE","assignment_staff_id":7,
        "reference_kind":"scheduling_service_day_log_attachment","provider_media_id":None,
        "object_owner":"scheduling","staging_owner":"scheduling","object_purpose":kind,"staging_purpose":kind,
        "object_subject":"CASE","staging_subject":"CASE","object_key":key,"staging_key":key,"staging_digest":DIGEST,
        "staging_state":"applied","object_actor":"staff:7","staging_actor":"staff:7",
        "staging_mime_type":"image/jpeg","staging_size_bytes":3}


@pytest.mark.parametrize("kind", ["baby_log_photo","meal_photo"])
@pytest.mark.parametrize("failure", [None,"orphan","actor","event","legacy_provider"])
def test_scheduling_true_submission_to_same_connection_maintenance_complete_without_photo_sending(monkeypatch,kind,failure):
    from infrastructure.mysql import service_day_log_photo_reference_repository as owner
    service,repository,events=application()
    repository.readback=replace(repository.readback,purpose=ControlledFilePurpose(kind))
    row=submitted_photo_row(kind)
    if failure=="actor":row["staging_actor"]="staff:8"
    if failure=="event":row["event_id"]=0
    if failure=="legacy_provider":row["provider_media_id"]="legacy-media"
    reference=_submitted_photo_reference(()) if failure=="orphan" else _submitted_photo_reference((row,))
    connection=Connection(events)
    actual=MySqlControlledFileWorkflowRepository(connection)
    actual.get_download_reference=repository.get_download_reference
    def factory(conn):
        assert conn is connection
        return SimpleNamespace(get_submitted_photo_reference=lambda _:reference)
    monkeypatch.setattr(owner,"MySqlSubmittedServiceDayLogPhotoRepository",factory)
    repository.reconciliation_reference_status=actual.reconciliation_reference_status
    result=service.reconcile(FILE,actor=command().actor,correlation_id=command().correlation_id)
    assert result["complete"] is (failure is None) and events==[]
    if failure is None:
        assert result["references"]=={"business_reference":"matched","owner_submission_reference":"matched","outbound_reference":"not_applicable"}
        assert result["owner_submission_reference"]=="scheduling-service-day-log:9"
        assert not any("provider" in key or "token" in key or "inbox" in key for key in result)
    else:
        assert result["references"]["outbound_reference"]=="unavailable"
        assert "owner_submission_reference" not in result


@pytest.mark.parametrize("field,value", [("file_id","cf_"+"d"*32),("version",2),("sha256_digest","d"*64),
    ("size_bytes",4),("mime_type","image/png"),("case_no","OTHER"),("attachment_kind","baby_log_photo"),("log_id",0)])
def test_scheduling_mapper_rejects_any_nonmatching_frozen_owner_tuple(field,value):
    service,repository,events=application()
    reference=replace(_submitted_photo_reference((submitted_photo_row("meal_photo"),)),**{field:value})
    repository.reconciliation_reference_status=lambda _:_scheduling_photo_reference_status(repository.readback,reference)
    result=service.reconcile(FILE,actor=command().actor,correlation_id=command().correlation_id)
    assert not result["complete"] and result["references"]["outbound_reference"]=="unavailable" and events==[]


def test_submission_status_without_actual_reference_or_unknown_extra_world_never_completes():
    service,repository,events=application()
    base={"business_reference":"matched","owner_submission_reference":"matched","outbound_reference":"not_applicable"}
    for extra in ({},{"owner_submission_reference_id":"arbitrary"},
        {"owner_submission_reference_id":"scheduling-service-day-log:9","other_required_world":"unavailable"}):
        repository.reconciliation_reference_status=lambda _:base|extra
        assert not service.reconcile(FILE,actor=command().actor,correlation_id=command().correlation_id)["complete"]
    assert events==[]


def test_reconciliation_catches_metadata_size_mismatch_and_never_writes_preview():
    app, repository, events = application()
    repository.readback = replace(repository.readback, size_bytes=4)
    result = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert result["storage_outcome"] == "digest_mismatch" and not result["complete"]
    assert events == [] and repository.observations == []


def test_reconciliation_formal_query_and_preview_apply_reach_original_consumer():
    service, repository, events = application()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(id=7, is_root=True, effective_capabilities=lambda: ())
    app.dependency_overrides[get_controlled_file_maintenance] = lambda: service
    with TestClient(app) as client:
        listing = client.get("/api/v1/data-center/reconciliation?limit=1")
        preview = client.post("/api/v1/data-center/reconciliation/preview", json={"file_id": FILE})
        assert listing.status_code == preview.status_code == 200
        assert events == [] and repository.observations == []
        result = client.post("/api/v1/data-center/reconciliation/apply", json={"file_id": FILE})
    assert result.status_code == 200 and result.json()["data"]["status"] == "review_required"
    assert events == ["begin", "commit"] and len(repository.observations) == 1


@pytest.mark.parametrize("root,status", [(False, 403), (True, 200)])
def test_actual_formal_cleanup_route_checks_root_and_uses_server_actor(root, status):
    app_service, repository, events = application()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(id=7, is_root=root, effective_capabilities=lambda: ())
    app.dependency_overrides[get_controlled_file_maintenance] = lambda: app_service
    with TestClient(app) as client:
        response = client.post("/api/v1/data-center/staging/cleanup", headers={"Idempotency-Key": "cleanup-test"},
            json={"staging_id": STAGE, "expected_staging_version": 1, "expected_sha256": DIGEST, "category": "expired"})
    assert response.status_code == status
    if root:
        assert response.json()["data"]["deleted_set"] == [STAGE]
        assert repository.stored is not None and events.count("bytes") == 1
    else:
        assert events == []


def test_actual_formal_route_rejects_arbitrary_path_and_client_actor():
    app_service, _, events = application()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(id=7, is_root=True, effective_capabilities=lambda: ())
    app.dependency_overrides[get_controlled_file_maintenance] = lambda: app_service
    with TestClient(app) as client:
        response = client.post("/api/v1/data-center/staging/cleanup", headers={"Idempotency-Key": "cleanup-test"},
            json={"staging_id": "../05-backups", "expected_staging_version": 1, "expected_sha256": DIGEST, "actor": "admin:other"})
    assert response.status_code == 422 and events == []


def test_real_composition_uses_one_connection_for_repository_and_original_uow(monkeypatch):
    import api.dependencies.controlled_files as dependencies
    events = []; connection = Connection(events)
    monkeypatch.setattr(dependencies, "get_connection", lambda: connection)
    monkeypatch.setattr(dependencies, "configured_storage_root", lambda: None)
    dependency = dependencies.get_controlled_file_maintenance()
    app = next(dependency)
    assert app.repository._connection is connection
    assert app.cleanup_workflow._unit_of_work_factory()._connection is connection
    assert app.reconciler._unit_of_work_factory()._connection is connection
    assert events == []
    dependency.close()
    assert events == ["close"]


def test_http_to_real_composition_to_original_uow_shares_connection_with_no_sql_ports(monkeypatch):
    import api.dependencies.controlled_files as dependencies
    events = []; connection = Connection(events)
    repository = Repository(events)
    def repository_port(actual_connection):
        assert actual_connection is connection
        return repository
    monkeypatch.setattr(dependencies, "get_connection", lambda: connection)
    monkeypatch.setattr(dependencies, "MySqlControlledFileWorkflowRepository", repository_port)
    monkeypatch.setattr(dependencies, "FileSystemControlledFileStorage", lambda *_args, **_kwargs: Storage(events))
    monkeypatch.setattr(dependencies, "SystemBusinessClock", lambda: FixedBusinessClock(NOW))
    monkeypatch.setattr(dependencies, "configured_storage_root", lambda: None)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(id=7, is_root=True, effective_capabilities=lambda: ())
    with TestClient(app) as client:
        result = client.post("/api/v1/data-center/staging/cleanup", headers={"Idempotency-Key": "cleanup-test"},
            json={"staging_id": STAGE, "expected_staging_version": 1, "expected_sha256": DIGEST})
    assert result.status_code == 200
    assert events == ["begin", "intent", "commit", "bytes", "begin", "terminal", "commit", "close"]


@pytest.mark.parametrize("limit", [0, 101, True])
def test_maintenance_query_rejects_unbounded_limit_before_database(limit):
    from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
    with pytest.raises(ValueError, match="limit"):
        MySqlControlledFileWorkflowRepository(Connection([])).list_readbacks(limit=limit)
