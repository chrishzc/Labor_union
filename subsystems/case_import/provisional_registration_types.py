"""
File: provisional_registration_types.py
Description: 定義 provisional LINE 登記的 Preview、衝突與套用結果。
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion


class ProvisionalRegistrationConflictError(RuntimeError):
    """The LINE identity already owns a different active registration."""


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
    client_id: int
    beclass_record_id: int
    client_name: str
    replayed: bool
    worker_wakeup_required: bool


__all__ = [
    "ProvisionalRegistrationConflict",
    "ProvisionalRegistrationConflictError",
    "ProvisionalRegistrationPreview",
    "ProvisionalRegistrationReceipt",
]
