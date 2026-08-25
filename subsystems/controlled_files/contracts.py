"""
File: contracts.py
Description: 定義共用受控檔案的唯讀探索、完整性讀取與 typed storage 錯誤契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ControlledFileStorageStatus(str, Enum):
    READY = "ready"
    UNCONFIGURED = "unconfigured"
    MOUNT_UNAVAILABLE = "mount_unavailable"
    READ_DENIED = "read_denied"


class ControlledFileStorageError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


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


__all__ = [
    "ControlledFileContent",
    "ControlledFileDiscoveryPage",
    "ControlledFileStorageError",
    "ControlledFileStoragePort",
    "ControlledFileStorageReadiness",
    "ControlledFileStorageStatus",
    "DiscoveredControlledFile",
]
