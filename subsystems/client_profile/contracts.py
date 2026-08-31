"""Typed contracts for Client profile Query/Preview/Apply workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from shared_kernel.fingerprints import PreviewFingerprint


class ClientProfileError(RuntimeError):
    """Base error for closed Client profile workflow outcomes."""


class ClientProfileNotFoundError(ClientProfileError):
    pass


class ClientProfileBindingError(ClientProfileError):
    pass


class ClientProfileStaleError(ClientProfileError):
    pass


class ClientProfileRequestConflictError(ClientProfileError):
    pass


class ClientProfilePermissionError(ClientProfileError):
    pass


@dataclass(frozen=True, slots=True)
class ClientBindingEvidence:
    """Minimal generic identity evidence consumed by the Client owner."""

    applicant_identity: str
    client_id: int
    binding_version: int
    roles: tuple[str, ...]
    complete: bool
    legal_customer_staff_dual_role: bool


class ClientBindingPort(Protocol):
    def read_current(
        self,
        applicant_identity: str,
        *,
        client_id: int,
        lock: bool = False,
    ) -> ClientBindingEvidence: ...


@dataclass(frozen=True, slots=True)
class ClientProfileView:
    client_id: int
    version: int
    values: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ClientProfileRequestView:
    request_id: int
    client_id: int
    line_user_id: str
    status: str
    request_version: int
    profile_version: int
    before: Mapping[str, str]
    requested: Mapping[str, str]
    reason: str
    created_at: object | None = None
    reviewed_at: object | None = None


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
class ClientProfileApplicantReceipt:
    request: ClientProfileRequestView
    preview_fingerprint: PreviewFingerprint
    idempotency_key: str
    replayed: bool
    readback: ClientProfileView


@dataclass(frozen=True, slots=True)
class ClientProfileApprovalReceipt:
    request: ClientProfileRequestView
    preview_fingerprint: PreviewFingerprint
    idempotency_key: str
    replayed: bool
    readback: ClientProfileView


__all__ = [
    "ClientProfileApprovalReceipt",
    "ClientProfileApplicantReceipt",
    "ClientBindingEvidence",
    "ClientBindingPort",
    "ClientProfileBindingError",
    "ClientProfileError",
    "ClientProfileNotFoundError",
    "ClientProfilePermissionError",
    "ClientProfilePreview",
    "ClientProfileRequestConflictError",
    "ClientProfileRequestView",
    "ClientProfileStaleError",
    "ClientProfileView",
]
