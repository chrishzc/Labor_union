"""Bounded root-only registry deletion coordination (spec 33, RD-1).

The API owns human authorization. This coordinator owns the sole outer commit;
the adapter supplies fresh signing facts and removes case-owned relations without
committing outside that transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext

RegistryKind = Literal["case"]


class RegistryDeletionNotFound(LookupError):
    pass


class RegistryDeletionConflict(ValueError):
    def __init__(self, code: str, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.blockers = blockers


@dataclass(frozen=True, slots=True)
class RegistryDeletionPreview:
    kind: RegistryKind
    identity: str
    version: int
    client_version: int | None
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegistryDeletionReceipt:
    kind: RegistryKind
    identity: str
    deleted: bool
    replayed: bool = False


class RegistryDeletionRepository(Protocol):
    def load(self, kind: RegistryKind, identity: str, *, for_update: bool) -> RegistryDeletionPreview: ...
    def claim(self, key: str, digest: str, kind: RegistryKind, identity: str, correlation: str) -> None: ...
    def receipt(self, key: str) -> dict[str, Any] | None: ...
    def delete(self, target: RegistryDeletionPreview) -> None: ...
    def save_receipt(self, key: str, digest: str, target: RegistryDeletionPreview, actor: str) -> None: ...


class RegistryDeletionApplication:
    def __init__(self, repository: RegistryDeletionRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, kind: RegistryKind, identity: str) -> RegistryDeletionPreview:
        return self._repository.load(kind, identity, for_update=False)

    def apply(
        self, kind: RegistryKind, identity: str, *, expected_version: int,
        expected_client_version: int | None, key: str, actor: ActorContext, correlation: str,
    ) -> RegistryDeletionReceipt:
        digest = fingerprint_payload({
            "family": "registry_delete/v1", "kind": kind, "identity": identity,
            "expected_version": expected_version, "expected_client_version": expected_client_version,
            "actor": actor.actor_id,
        }).value
        with self._unit_of_work_factory() as uow:
            self._repository.claim(key, digest, kind, identity, correlation)
            saved = self._repository.receipt(key)
            if saved is not None:
                if saved["digest"] != digest:
                    raise RegistryDeletionConflict("registry_deletion_idempotency_mismatch")
                result = saved["result"]
                uow.commit()
                return RegistryDeletionReceipt(result["kind"], result["identity"], True, True)
            target = self._repository.load(kind, identity, for_update=True)
            if target.version != expected_version or target.client_version != expected_client_version:
                raise RegistryDeletionConflict("registry_deletion_stale_version")
            if target.blockers:
                raise RegistryDeletionConflict("registry_deletion_signed", target.blockers)
            self._repository.delete(target)
            self._repository.save_receipt(key, digest, target, actor.actor_id)
            uow.commit()
        return RegistryDeletionReceipt(kind, identity, True)
