"""Typed contracts for Client profile Query/Preview/Apply workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint


class ClientProfileError(RuntimeError):
    """Base error for closed Client profile workflow outcomes."""


class ClientProfileNotFoundError(ClientProfileError):
    pass


class ClientProfileStaleError(ClientProfileError):
    pass


class ClientProfileRequestConflictError(ClientProfileError):
    pass


@dataclass(frozen=True, slots=True)
class ClientProfileView:
    client_id: int
    version: int
    values: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ClientProfilePreview:
    client_id: int
    current_version: int
    before: Mapping[str, str]
    requested: Mapping[str, str]
    preview_fingerprint: PreviewFingerprint
    apply_ready: bool = True
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClientProfileAdminReceipt:
    case_no: str
    resulting_version: int
    changed_fields: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    idempotency_key: str
    replayed: bool
    readback: ClientProfileView


__all__ = [
    "ClientProfileAdminReceipt",
    "ClientProfileError",
    "ClientProfileNotFoundError",
    "ClientProfilePreview",
    "ClientProfileRequestConflictError",
    "ClientProfileStaleError",
    "ClientProfileView",
]
