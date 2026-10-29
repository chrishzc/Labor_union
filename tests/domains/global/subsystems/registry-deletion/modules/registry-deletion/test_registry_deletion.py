"""RD-A1..4: cross-owner authority, fresh guards, atomic deletion and replay."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import require_admin
from api.dependencies.registry_deletion import get_registry_deletion_application, require_registry_deletion_root
from api.routes.registry_deletion import case_router, _raise_error
from infrastructure.mysql.registry_deletion_repository import MySqlRegistryDeletionRepository
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.registry_deletion import (
    RegistryDeletionApplication, RegistryDeletionConflict, RegistryDeletionNotFound, RegistryDeletionPreview,
)


class Repository:
    def __init__(self, kind="case"):
        self.target = RegistryDeletionPreview(kind, "CASE-7", 2, 4, ())
        self.claims = {}
        self.receipts = {}
        self.deleted = False
        self.fail_audit = False
        self.locked_reads = []

    def load(self, kind, identity, *, for_update):
        self.locked_reads.append(for_update)
        if self.deleted:
            raise RegistryDeletionNotFound()
        return self.target

    def claim(self, key, digest, *_):
        if self.claims.setdefault(key, digest) != digest:
            raise RegistryDeletionConflict("registry_deletion_idempotency_mismatch")

    def receipt(self, key):
        return self.receipts.get(key)

    def delete(self, target):
        assert self.locked_reads[-1] is True
        self.deleted = True

    def save_receipt(self, key, digest, target, actor):
        if self.fail_audit:
            raise RuntimeError("audit storage unavailable")
        self.receipts[key] = {"digest": digest, "result": {"kind": target.kind, "identity": target.identity}}


class Uow:
    def __init__(self, repo):
        self.repo = repo
        self.commits = 0

    def __enter__(self):
        self.before = deepcopy((self.repo.claims, self.repo.receipts, self.repo.deleted))
        return self

    def __exit__(self, error_type, *_):
        if error_type or not self.commits:
            self.repo.claims, self.repo.receipts, self.repo.deleted = self.before

    def commit(self):
        self.commits += 1


def application(kind="case"):
    repo = Repository(kind)
    uow = Uow(repo)
    return RegistryDeletionApplication(repo, lambda: uow), repo, uow


def apply(app, *, kind="case", version=2, client_version=4, key="delete-7"):
    return app.apply(kind, "CASE-7", expected_version=version,
                     expected_client_version=client_version, key=key,
                     actor=ActorContext("admin:1", ()), correlation="corr-7")


@pytest.mark.parametrize("principal", [
    AdminPrincipal(2, "root", "Same name", "system_admin", is_root=False),
    AdminPrincipal(None, "development-bypass", "Bypass", "system_admin", is_root=True),
    AdminPrincipal(1, "root", "Disabled", "system_admin", is_root=True, enabled=False),
])
def test_only_enabled_persisted_root_can_delete(principal):
    with pytest.raises(HTTPException) as caught:
        require_registry_deletion_root(principal)
    assert caught.value.status_code == 403
    root = AdminPrincipal(1, "operator", "Root", "system_admin", is_root=True)
    assert require_registry_deletion_root(root) is root


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/cases/CASE-7/deletion", None),
    ("POST", "/cases/CASE-7/deletion/apply", {"expected_version": 2, "expected_client_version": 4}),
])
def test_authorization_runs_before_opening_deletion_connection(monkeypatch, method, path, body):
    api = FastAPI()
    api.include_router(case_router, prefix="/cases")
    api.dependency_overrides[require_admin] = lambda: AdminPrincipal(2, "root", "Not root", "system_admin")
    def forbidden_connection():
        pytest.fail("non-root must not open the writer connection")
    monkeypatch.setattr("api.dependencies.registry_deletion.get_connection", forbidden_connection)
    response = TestClient(api).request(method, path, json=body, headers={"Idempotency-Key": "x", "X-Correlation-ID": "c"})
    assert response.status_code == 403


def test_root_http_receipt_and_unauthenticated_refusal():
    api = FastAPI()
    api.include_router(case_router, prefix="/cases")
    root = AdminPrincipal(1, "operator", "Root", "system_admin", is_root=True)
    api.dependency_overrides[require_admin] = lambda: root
    deletion_app, repo, _ = application()
    api.dependency_overrides[get_registry_deletion_application] = lambda: deletion_app
    client = TestClient(api)
    preview = client.get("/cases/CASE-7/deletion")
    assert preview.status_code == 200
    assert preview.json()["data"]["blockers"] == []
    response = client.post("/cases/CASE-7/deletion/apply", json={"expected_version": 2, "expected_client_version": 4},
                           headers={"Idempotency-Key": "http-delete", "X-Correlation-ID": "corr"})
    assert response.status_code == 200
    assert response.json()["data"] == {"kind": "case", "identity": "CASE-7", "deleted": True, "replayed": False}
    assert repo.deleted
    def unauthorized(): raise HTTPException(status_code=401)
    api.dependency_overrides[require_admin] = unauthorized
    assert client.post("/cases/CASE-7/deletion/apply", json={"expected_version": 2, "expected_client_version": 4},
                       headers={"Idempotency-Key": "other", "X-Correlation-ID": "corr"}).status_code == 401


def test_preview_zero_writes_then_success_replays_after_root_is_gone():
    app, repo, uow = application()
    assert app.preview("case", "CASE-7").blockers == ()
    assert not repo.claims and not repo.receipts and uow.commits == 0
    assert apply(app).deleted is True
    assert repo.deleted and uow.commits == 1
    reads = list(repo.locked_reads)
    assert apply(app).replayed is True
    assert repo.locked_reads == reads
    with pytest.raises(RegistryDeletionConflict, match="idempotency_mismatch"):
        apply(app, version=9)


def test_signature_after_preview_blocks_without_delete_or_receipt():
    app, repo, uow = application()
    app.preview("case", "CASE-7")
    repo.target = replace(repo.target, blockers=("已有月嫂或客戶簽回，禁止刪除",))
    with pytest.raises(RegistryDeletionConflict, match="signed"):
        apply(app)
    assert not repo.deleted and not repo.receipts and not repo.claims and uow.commits == 0


@pytest.mark.parametrize("version", [0, 1, 3])
def test_stale_version_cannot_delete(version):
    app, repo, uow = application()
    with pytest.raises(RegistryDeletionConflict, match="stale_version"):
        apply(app, version=version)
    assert not repo.deleted and not repo.claims and not uow.commits


def test_receipt_failure_rolls_back_root_and_command_claim():
    app, repo, uow = application()
    repo.fail_audit = True
    with pytest.raises(RuntimeError, match="audit storage"):
        apply(app)
    assert not repo.deleted and not repo.receipts and not repo.claims and not uow.commits


@pytest.mark.parametrize("error,code", [
    (IntegrityError(1451, "sensitive SQL must not leak"), "registry_deletion_integrity_conflict"),
    (OperationalError(1213, "deadlock"), "registry_deletion_concurrent_conflict"),
    (OperationalError(1205, "timeout"), "registry_deletion_concurrent_conflict"),
])
def test_fk_and_lock_races_are_closed_conflicts(error, code):
    with pytest.raises(HTTPException) as caught:
        _raise_error(error, "corr")
    assert caught.value.status_code == 409
    assert caught.value.detail["error"]["code"] == code
    assert "sensitive SQL" not in str(caught.value.detail)



def test_staff_permanent_deletion_endpoints_are_removed():
    from api.routes.staff_registry_mutation import router
    api = FastAPI()
    api.include_router(router)
    assert "/api/v1/staff/{staff_id}/profile/preview" in api.openapi()["paths"]
    client = TestClient(api)
    assert client.get("/api/v1/staff/7/deletion").status_code == 404
    assert client.post("/api/v1/staff/7/deletion/apply", json={"expected_version": 0}).status_code == 404


def test_database_guard_rejection_rolls_back_and_is_a_known_cancelled_result():
    application, repo, uow = globals()["application"]()
    error = OperationalError(1644, "private_history_table records cannot be deleted")
    def reject(_):
        raise error
    repo.delete = reject
    with pytest.raises(OperationalError):
        apply(application)
    assert not repo.deleted and not repo.claims and not repo.receipts and uow.commits == 0
    with pytest.raises(HTTPException) as caught:
        _raise_error(error, "guard-test")
    assert caught.value.status_code == 409
    assert caught.value.detail["error"]["code"] == "registry_deletion_guard_rejected"
    assert "原資料已保留" in caught.value.detail["error"]["message"]
    assert "private_history_table" not in str(caught.value.detail)
