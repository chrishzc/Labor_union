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
from infrastructure.db.controlled_file_repository import _gc_candidate, _require_cleanup_safe, _contract_reference_status, _GC_CANDIDATES_SQL
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
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT, mime_type="application/pdf")
    reference = FinalContractFileReference(FILE, "CASE", DIGEST, 3, True, True, 1)
    if field is not None: reference = replace(reference, **{field: value})
    repository.reconciliation_reference_status = lambda _: _contract_reference_status(repository.readback, reference)
    result = app.reconcile(FILE, actor=command().actor, correlation_id=command().correlation_id)
    assert (result["references"]["frozen_completion_reference"] == "matched") is complete
    assert result["references"]["outbound_reference"] == "unavailable" and not result["complete"]


@pytest.mark.parametrize("field,value,matched", [
    (None, None, True), ("file_id", "cf_" + "d"*32, False), ("size_bytes", 4, False),
    ("mime_type", "image/png", False), ("target", SignedContractDocumentTarget("client", None, 8), False),
])
def test_contract_owner_projection_binds_receipt_member_to_size_mime_and_registered_target(field, value, matched):
    target = SignedContractDocumentTarget("client", None, 7)
    row = {"opaque_object_id": FILE, "object_key": "signed-contract:SESSION:client:v7",
        "external_signing_session_id": "SESSION", "case_no": "CASE", "content_sha256": DIGEST,
        "size_bytes": 3, "is_current": 1, "receipt_count": 1}
    values = dict(file_id=FILE, version=1, size_bytes=3, mime_type="application/pdf", target=target)
    if field is not None: values[field] = value
    projected = _final_contract_file_reference(row, (SimpleNamespace(**values),))
    assert projected.completion_receipt_present is matched
    assert projected.file_version == (1 if matched else None)


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
