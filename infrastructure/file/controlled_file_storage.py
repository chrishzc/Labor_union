"""
File: controlled_file_storage.py
Description: 以既有 NAS 掛載根目錄提供受控唯讀檔案探索與 digest 驗證，不建立或暴露實體路徑。
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from subsystems.controlled_files.contracts import (
    ControlledFileContent,
    ControlledFileDiscoveryPage,
    ControlledFileStorageError,
    ControlledFileStorageReadiness,
    ControlledFileStorageStatus,
    DiscoveredControlledFile,
)


_IGNORED_SUFFIXES = frozenset({".crdownload", ".partial", ".tmp"})
_MAX_DISCOVERY_LIMIT = 100
_DEFAULT_MAX_READ_BYTES = 20 * 1024 * 1024


class FileSystemControlledFileStorage:
    def __init__(
        self,
        storage_root: str | Path | None,
        *,
        settle_seconds: float = 5.0,
        max_read_bytes: int = _DEFAULT_MAX_READ_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if settle_seconds < 0:
            raise ValueError("settle_seconds must not be negative")
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be positive")
        configured = str(storage_root).strip() if storage_root is not None else ""
        self._configured_root = Path(configured) if configured else None
        self._settle_seconds = settle_seconds
        self._max_read_bytes = max_read_bytes
        self._clock = clock

    def readiness(self) -> ControlledFileStorageReadiness:
        if self._configured_root is None:
            return ControlledFileStorageReadiness(
                ControlledFileStorageStatus.UNCONFIGURED,
                "受控檔案儲存位置尚未設定",
            )
        try:
            root = self._configured_root.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return ControlledFileStorageReadiness(
                ControlledFileStorageStatus.MOUNT_UNAVAILABLE,
                "受控檔案儲存目前無法連線",
            )
        if not root.is_dir():
            return ControlledFileStorageReadiness(
                ControlledFileStorageStatus.MOUNT_UNAVAILABLE,
                "受控檔案儲存目前無法連線",
            )
        if not os.access(root, os.R_OK):
            return ControlledFileStorageReadiness(
                ControlledFileStorageStatus.READ_DENIED,
                "受控檔案儲存目前無法讀取",
            )
        return ControlledFileStorageReadiness(
            ControlledFileStorageStatus.READY,
            "受控檔案儲存可讀取",
        )

    def discover(
        self,
        *,
        limit: int,
        after: str | None = None,
    ) -> ControlledFileDiscoveryPage:
        if isinstance(limit, bool) or not 1 <= limit <= _MAX_DISCOVERY_LIMIT:
            raise ControlledFileStorageError(
                "controlled_file_query_invalid",
                "檔案查詢筆數必須介於 1 與 100",
                retryable=False,
            )
        if after is not None:
            _validate_object_reference(after)
        root = self._require_ready_root()
        references = sorted(self._discover_references(root))
        if after is not None:
            references = [reference for reference in references if reference > after]
        selected = references[: limit + 1]
        next_after = selected[limit - 1] if len(selected) > limit else None
        items = tuple(_projection(reference) for reference in selected[:limit])
        return ControlledFileDiscoveryPage(items=items, next_after=next_after)

    def read_verified(
        self,
        object_reference: str,
        *,
        expected_sha256: str | None = None,
    ) -> ControlledFileContent:
        reference = _validate_object_reference(object_reference)
        if expected_sha256 is not None and not _is_sha256(expected_sha256):
            raise ControlledFileStorageError(
                "controlled_file_digest_invalid",
                "檔案完整性識別格式無效",
                retryable=False,
            )
        root = self._require_ready_root()
        target = self._resolve_target(root, reference)
        try:
            before = target.stat()
        except FileNotFoundError as error:
            raise ControlledFileStorageError(
                "controlled_file_not_found",
                "指定檔案不存在",
                retryable=False,
            ) from error
        except PermissionError as error:
            raise ControlledFileStorageError(
                "controlled_file_read_denied",
                "指定檔案目前無法讀取",
                retryable=False,
            ) from error
        if not target.is_file():
            raise ControlledFileStorageError(
                "controlled_file_not_found",
                "指定檔案不存在",
                retryable=False,
            )
        if self._clock() - before.st_mtime < self._settle_seconds:
            raise ControlledFileStorageError(
                "controlled_file_still_writing",
                "指定檔案仍在寫入，請稍後重試",
                retryable=True,
            )
        if before.st_size > self._max_read_bytes:
            raise ControlledFileStorageError(
                "controlled_file_too_large",
                "指定檔案超過本次讀取上限",
                retryable=False,
            )
        try:
            content = target.read_bytes()
            after = target.stat()
        except PermissionError as error:
            raise ControlledFileStorageError(
                "controlled_file_read_denied",
                "指定檔案目前無法讀取",
                retryable=False,
            ) from error
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ControlledFileStorageError(
                "controlled_file_changed_during_read",
                "指定檔案在讀取期間發生變更，請稍後重試",
                retryable=True,
            )
        digest = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256.lower():
            raise ControlledFileStorageError(
                "controlled_file_digest_mismatch",
                "指定檔案完整性驗證失敗",
                retryable=False,
            )
        content_type = mimetypes.guess_type(reference.name)[0] or "application/octet-stream"
        return ControlledFileContent(
            object_reference=reference.as_posix(),
            filename=reference.name,
            content_type=content_type,
            content=content,
            content_sha256=digest,
        )

    def _require_ready_root(self) -> Path:
        readiness = self.readiness()
        if not readiness.ready:
            retryable = readiness.status in {
                ControlledFileStorageStatus.MOUNT_UNAVAILABLE,
                ControlledFileStorageStatus.READ_DENIED,
            }
            raise ControlledFileStorageError(
                f"controlled_file_storage_{readiness.status.value}",
                readiness.reason,
                retryable=retryable,
            )
        assert self._configured_root is not None
        return self._configured_root.resolve(strict=True)

    def _discover_references(self, root: Path):
        try:
            for current_root, directory_names, filenames in os.walk(root, followlinks=False):
                current = Path(current_root)
                directory_names[:] = sorted(
                    name
                    for name in directory_names
                    if not name.startswith(".") and not (current / name).is_symlink()
                )
                for filename in sorted(filenames):
                    target = current / filename
                    if _should_ignore(target) or target.is_symlink():
                        continue
                    try:
                        stat = target.stat()
                    except FileNotFoundError:
                        continue
                    except PermissionError as error:
                        raise ControlledFileStorageError(
                            "controlled_file_storage_read_denied",
                            "受控檔案儲存目前無法完整讀取",
                            retryable=True,
                        ) from error
                    except OSError as error:
                        raise ControlledFileStorageError(
                            "controlled_file_storage_mount_unavailable",
                            "受控檔案儲存目前無法完整讀取",
                            retryable=True,
                        ) from error
                    if not target.is_file() or self._clock() - stat.st_mtime < self._settle_seconds:
                        continue
                    reference = target.relative_to(root).as_posix()
                    _validate_object_reference(reference)
                    yield reference
        except PermissionError as error:
            raise ControlledFileStorageError(
                "controlled_file_storage_read_denied",
                "受控檔案儲存目前無法讀取",
                retryable=True,
            ) from error

    @staticmethod
    def _resolve_target(root: Path, reference: PurePosixPath) -> Path:
        candidate = root.joinpath(*reference.parts)
        if any(path.is_symlink() for path in _path_chain(root, candidate)):
            raise ControlledFileStorageError(
                "controlled_file_reference_invalid",
                "檔案識別超出受控儲存範圍",
                retryable=False,
            )
        try:
            target = candidate.resolve(strict=True)
            target.relative_to(root)
        except FileNotFoundError as error:
            raise ControlledFileStorageError(
                "controlled_file_not_found",
                "指定檔案不存在",
                retryable=False,
            ) from error
        except (OSError, ValueError) as error:
            raise ControlledFileStorageError(
                "controlled_file_reference_invalid",
                "檔案識別超出受控儲存範圍",
                retryable=False,
            ) from error
        return target


def _validate_object_reference(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or ":" in value
    ):
        raise ControlledFileStorageError(
            "controlled_file_reference_invalid",
            "檔案識別格式無效",
            retryable=False,
        )
    reference = PurePosixPath(value)
    if reference.is_absolute() or any(part in {"", ".", ".."} for part in reference.parts):
        raise ControlledFileStorageError(
            "controlled_file_reference_invalid",
            "檔案識別格式無效",
            retryable=False,
        )
    return reference


def _projection(reference: str) -> DiscoveredControlledFile:
    parsed = PurePosixPath(reference)
    logical_folder = parsed.parent.as_posix() if parsed.parent != PurePosixPath(".") else ""
    return DiscoveredControlledFile(
        object_reference=reference,
        logical_folder=logical_folder,
        filename=parsed.name,
    )


def _should_ignore(target: Path) -> bool:
    return target.name.startswith(".") or target.suffix.lower() in _IGNORED_SUFFIXES


def _path_chain(root: Path, candidate: Path):
    current = candidate
    chain = []
    while current != root:
        chain.append(current)
        if current.parent == current:
            break
        current = current.parent
    return reversed(chain)


def _is_sha256(value: str) -> bool:
    normalized = value.lower()
    return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)


__all__ = ["FileSystemControlledFileStorage"]
