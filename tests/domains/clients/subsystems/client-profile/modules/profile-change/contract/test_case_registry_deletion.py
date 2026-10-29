"""Case deletion preserves the canonical Client binding and fresh owner versions."""

import pytest
from fastapi import HTTPException

from api.routes.registry_deletion import _apply
from api.schemas.registry_deletion import RegistryDeletionApplyRequest
from infrastructure.mysql.registry_deletion_repository import MySqlRegistryDeletionRepository
from shared_kernel.identities import ActorContext
from subsystems.registry_deletion import RegistryDeletionApplication, RegistryDeletionConflict, RegistryDeletionPreview


class CaseRepository:
    def __init__(self):
        self.target = RegistryDeletionPreview("case", "CASE-7", 2, 4, ())
        self.deleted = False
        self.saved = False

    def claim(self, *_): pass
    def receipt(self, *_): return None
    def load(self, *_, for_update):
        assert for_update
        return self.target
    def delete(self, target): self.deleted = True
    def save_receipt(self, *_): self.saved = True


class Uow:
    def __init__(self): self.committed = False
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): self.committed = True


@pytest.mark.parametrize("client_version,blocked", [(4, False), (3, True), (None, True)])
def test_case_delete_checks_client_version_as_well_as_order_version(client_version, blocked):
    repo, uow = CaseRepository(), Uow()
    app = RegistryDeletionApplication(repo, lambda: uow)
    def action():
        return app.apply("case", "CASE-7", expected_version=2, expected_client_version=client_version,
                         key="case-delete", actor=ActorContext("admin:1", ()), correlation="corr")
    if blocked:
        with pytest.raises(RegistryDeletionConflict, match="stale_version"): action()
        assert not repo.deleted and not repo.saved and not uow.committed
    else:
        assert action().deleted and repo.deleted and repo.saved and uow.committed


def test_case_api_requires_client_version_before_calling_application():
    with pytest.raises(HTTPException) as caught:
        _apply("case", "CASE-7", RegistryDeletionApplyRequest(expected_version=2), "key", "corr", None, None)
    assert caught.value.status_code == 422
