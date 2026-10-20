"""
File: provisional_registration_types.py
Description: 定義 provisional LINE 登記的 Preview、衝突與套用結果。
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion
from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate


class ProvisionalRegistrationConflictError(RuntimeError):
    """The LINE identity already owns a different active registration."""


class ProvisionalRegistrationStorageError(RuntimeError):
    """Storage or transaction failure at the provisional-registration boundary."""


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationConflict:
    registration_id: int
    conflict_id: int


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationPreview:
    status: str
    expected_binding_version: ExpectedVersion
    payload_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationReceipt:
    registration_id: int
    client_id: int | None
    beclass_record_id: int | None
    client_name: str
    replayed: bool
    worker_wakeup_required: bool


@dataclass(frozen=True, slots=True)
class RegistrationApplicationSnapshot:
    registration_id: int
    version: int
    candidate: ProvisionalRegistrationCandidate
    client_id: int | None
    beclass_record_id: int | None
    approved_by_actor: str | None


__all__ = [
    "ProvisionalRegistrationConflict",
    "ProvisionalRegistrationConflictError",
    "ProvisionalRegistrationStorageError",
    "ProvisionalRegistrationPreview",
    "ProvisionalRegistrationReceipt",
    "RegistrationApplicationSnapshot",
]
