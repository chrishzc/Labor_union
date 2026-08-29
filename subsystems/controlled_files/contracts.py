"""
File: contracts.py
Description: 定義受控檔案的唯讀探索、完整性讀取與系統 staging 契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class ControlledFileStorageStatus(str, Enum):
    READY = "ready"
    UNCONFIGURED = "unconfigured"
    MOUNT_UNAVAILABLE = "mount_unavailable"
    READ_DENIED = "read_denied"


class ControlledFileStorageError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        observed_sha256: str | None = None,
        observed_size_bytes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.observed_sha256 = observed_sha256
        self.observed_size_bytes = observed_size_bytes


class ControlledFileStagingRegistrationStatus(str, Enum):
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    UNKNOWN = "unknown"


class ControlledFileStagingCleanupReason(str, Enum):
    EXPIRED = "expired"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class ControlledFileStorageReadiness:
    status: ControlledFileStorageStatus
    reason: str

    @property
    def ready(self) -> bool:
        return self.status is ControlledFileStorageStatus.READY


@dataclass(frozen=True, slots=True)
class DiscoveredControlledFile:
    object_reference: str
    logical_folder: str
    filename: str


@dataclass(frozen=True, slots=True)
class ControlledFileDiscoveryPage:
    items: tuple[DiscoveredControlledFile, ...]
    next_after: str | None


@dataclass(frozen=True, slots=True)
class ControlledFileContent:
    object_reference: str
    filename: str
    content_type: str
    content: bytes
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ControlledFileStagingResult:
    staging_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256_digest: str
    expires_at: datetime
    replayed: bool


@dataclass(frozen=True, slots=True)
class ControlledFileStagingContent:
    staging_id: str
    content: bytes
    sha256_digest: str
    expires_at: datetime


class ControlledFileStoragePort(Protocol):
    def readiness(self) -> ControlledFileStorageReadiness: ...

    def discover(
        self,
        *,
        limit: int,
        after: str | None = None,
    ) -> ControlledFileDiscoveryPage: ...

    def read_verified(
        self,
        object_reference: str,
        *,
        expected_sha256: str | None = None,
    ) -> ControlledFileContent: ...

    def put_staged(
        self,
        *,
        idempotency_key: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> ControlledFileStagingResult: ...

    def read_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent: ...

    def read_registered_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent: ...

    def finalize_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent: ...

    def cleanup_staged(
        self,
        staging_id: str,
        *,
        registration_status: ControlledFileStagingRegistrationStatus,
        reason: ControlledFileStagingCleanupReason,
        expected_sha256: str,
    ) -> bool: ...


__all__ = [
    "ControlledFileContent",
    "ControlledFileDiscoveryPage",
    "ControlledFileStorageError",
    "ControlledFileStoragePort",
    "ControlledFileStorageReadiness",
    "ControlledFileStorageStatus",
    "ControlledFileStagingCleanupReason",
    "ControlledFileStagingContent",
    "ControlledFileStagingRegistrationStatus",
    "ControlledFileStagingResult",
    "DiscoveredControlledFile",
]
