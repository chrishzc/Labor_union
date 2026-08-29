"""
File: controlled_file_storage.py
Description: 以受控掛載根目錄提供唯讀探索與系統 staging，不暴露實體 locator。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from subsystems.controlled_files.contracts import (
    ControlledFileContent,
    ControlledFileDiscoveryPage,
    ControlledFileStorageError,
    ControlledFileStorageReadiness,
    ControlledFileStorageStatus,
    ControlledFileStagingCleanupReason,
    ControlledFileStagingContent,
    ControlledFileStagingRegistrationStatus,
    ControlledFileStagingResult,
    DiscoveredControlledFile,
)


_IGNORED_SUFFIXES = frozenset({".crdownload", ".partial", ".tmp"})
_MAX_DISCOVERY_LIMIT = 100
_DEFAULT_MAX_READ_BYTES = 20 * 1024 * 1024
_DEFAULT_MAX_STAGING_BYTES = 20 * 1024 * 1024
_STAGING_TTL = timedelta(hours=24)
_STAGING_DIRECTORY = ".controlled-file-staging"
_STAGING_ID_PREFIX = "cfs_"


class FileSystemControlledFileStorage:
    def __init__(
        self,
        storage_root: str | Path | None,
        *,
        settle_seconds: float = 5.0,
        max_read_bytes: int = _DEFAULT_MAX_READ_BYTES,
        max_staging_bytes: int = _DEFAULT_MAX_STAGING_BYTES,
        staging_ttl: timedelta = _STAGING_TTL,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if settle_seconds < 0:
            raise ValueError("settle_seconds must not be negative")
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be positive")
        if max_staging_bytes <= 0:
            raise ValueError("max_staging_bytes must be positive")
        if staging_ttl <= timedelta(0):
            raise ValueError("staging_ttl must be positive")
        configured = str(storage_root).strip() if storage_root is not None else ""
        self._configured_root = Path(configured) if configured else None
        self._settle_seconds = settle_seconds
        self._max_read_bytes = max_read_bytes
        self._max_staging_bytes = max_staging_bytes
        self._staging_ttl = staging_ttl
        self._clock = clock

    @property
    def staging_ttl(self) -> timedelta:
        """Return the operational staging TTL without exposing a storage locator."""
        return self._staging_ttl

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

    def put_staged(
        self,
        *,
        idempotency_key: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> ControlledFileStagingResult:
        _validate_staging_input(
            idempotency_key=idempotency_key,
            filename=filename,
            mime_type=mime_type,
            content=content,
            max_bytes=self._max_staging_bytes,
        )
        root = self._require_ready_root()
        staging_root = self._ensure_staging_layout(root)
        digest = hashlib.sha256(content).hexdigest()
        normalized_mime = mime_type.lower()
        fingerprint = _staging_fingerprint(
            filename=filename,
            mime_type=normalized_mime,
            size_bytes=len(content),
            sha256_digest=digest,
        )
        idempotency_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        index_path = staging_root / "idempotency" / f"{idempotency_digest}.json"
        staging_id = f"{_STAGING_ID_PREFIX}{uuid.uuid4().hex}"
        object_directory = self._create_staging_object_directory(staging_root, staging_id)
        now = datetime.fromtimestamp(self._clock(), timezone.utc)
        expires_at = now + self._staging_ttl
        metadata = {
            "schema": "controlled-file-staging.v1",
            "staging_id": staging_id,
            "filename": filename,
            "mime_type": normalized_mime,
            "size_bytes": len(content),
            "sha256_digest": digest,
            "canonical_fingerprint": fingerprint,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        try:
            _write_bytes_exclusive(object_directory / "payload.bin", content)
            _write_json_exclusive(object_directory / "metadata.json", metadata)
            try:
                _write_json_exclusive(
                    index_path,
                    {"staging_id": staging_id, "canonical_fingerprint": fingerprint},
                )
            except FileExistsError:
                existing = _read_json(index_path)
                self._remove_unindexed_candidate(object_directory)
                if existing.get("canonical_fingerprint") != fingerprint:
                    raise ControlledFileStorageError(
                        "controlled_file_staging_idempotency_conflict",
                        "相同 staging 重播識別對應不同內容",
                        retryable=False,
                    )
                return self._load_staging_result(
                    root,
                    str(existing.get("staging_id", "")),
                    replayed=True,
                )
        except ControlledFileStorageError:
            self._remove_unindexed_candidate(object_directory)
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._remove_unindexed_candidate(object_directory)
            raise ControlledFileStorageError(
                "controlled_file_staging_write_failed",
                "staging 檔案目前無法寫入",
                retryable=isinstance(error, OSError),
            ) from error
        return _staging_result_from_metadata(metadata, replayed=False)

    def read_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent:
        _validate_staging_id(staging_id)
        if not _is_sha256(expected_sha256):
            raise ControlledFileStorageError(
                "controlled_file_digest_invalid",
                "檔案完整性識別格式無效",
                retryable=False,
            )
        root = self._require_ready_root()
        metadata, content = self._read_staging_record(root, staging_id)
        expires_at = _parse_utc_datetime(metadata.get("expires_at"))
        now = datetime.fromtimestamp(self._clock(), timezone.utc)
        if now >= expires_at:
            raise ControlledFileStorageError(
                "controlled_file_staging_expired",
                "staging 檔案已過期",
                retryable=False,
            )
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha256.lower() or digest != metadata.get("sha256_digest"):
            raise ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "staging 檔案完整性驗證失敗",
                retryable=False,
            )
        return ControlledFileStagingContent(
            staging_id=staging_id,
            content=content,
            sha256_digest=digest,
            expires_at=expires_at,
        )

    def read_registered_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent:
        _validate_staging_id(staging_id)
        if not _is_sha256(expected_sha256):
            raise ControlledFileStorageError(
                "controlled_file_digest_invalid",
                "檔案完整性識別格式無效",
                retryable=False,
            )
        root = self._require_ready_root()
        metadata, content = self._read_staging_record(root, staging_id)
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha256.lower() or digest != metadata.get("sha256_digest"):
            raise ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "registered 檔案完整性驗證失敗",
                retryable=False,
                observed_sha256=digest,
                observed_size_bytes=len(content),
            )
        return ControlledFileStagingContent(
            staging_id=staging_id,
            content=content,
            sha256_digest=digest,
            expires_at=_parse_utc_datetime(metadata.get("expires_at")),
        )

    def finalize_staged(
        self,
        staging_id: str,
        *,
        expected_sha256: str,
    ) -> ControlledFileStagingContent:
        """Verify an applied object after DB commit.

        The filesystem adapter deliberately does not rename or delete bytes here:
        the 1004 schema stores the staging locator as the immutable object source.
        Finalization is therefore an idempotent integrity check; a future durable
        intent/reconciler may call it again without changing object identity.
        """
        return self.read_registered_staged(
            staging_id,
            expected_sha256=expected_sha256,
        )

    def cleanup_staged(
        self,
        staging_id: str,
        *,
        registration_status: ControlledFileStagingRegistrationStatus,
        reason: ControlledFileStagingCleanupReason,
        expected_sha256: str,
    ) -> bool:
        _validate_staging_id(staging_id)
        if registration_status is not ControlledFileStagingRegistrationStatus.UNREGISTERED:
            raise ControlledFileStorageError(
                "controlled_file_staging_cleanup_forbidden",
                "只允許清理未登錄的 system-owned staging 檔案",
                retryable=False,
            )
        if not isinstance(reason, ControlledFileStagingCleanupReason):
            raise ControlledFileStorageError(
                "controlled_file_staging_cleanup_reason_invalid",
                "staging 清理原因無效",
                retryable=False,
            )
        if not _is_sha256(expected_sha256):
            raise ControlledFileStorageError(
                "controlled_file_digest_invalid",
                "檔案完整性識別格式無效",
                retryable=False,
            )
        root = self._require_ready_root()
        metadata, content = self._read_staging_record(root, staging_id, missing_ok=True)
        if not metadata:
            return False
        expires_at = _parse_utc_datetime(metadata.get("expires_at"))
        now = datetime.fromtimestamp(self._clock(), timezone.utc)
        if reason is ControlledFileStagingCleanupReason.EXPIRED and now < expires_at:
            raise ControlledFileStorageError(
                "controlled_file_staging_not_expired",
                "staging 檔案尚未過期",
                retryable=False,
            )
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha256.lower() or digest != metadata.get("sha256_digest"):
            raise ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "staging 檔案完整性驗證失敗",
                retryable=False,
            )
        object_directory = self._staging_object_directory(root, staging_id)
        payload_path = object_directory / "payload.bin"
        try:
            payload_path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ControlledFileStorageError(
                "controlled_file_staging_cleanup_failed",
                "staging 檔案清理失敗，需要對帳",
                retryable=True,
            ) from error
        return True

    def _ensure_staging_layout(self, root: Path) -> Path:
        staging_root = root / _STAGING_DIRECTORY
        try:
            for directory in (staging_root, staging_root / "objects", staging_root / "idempotency"):
                if directory.is_symlink():
                    raise ControlledFileStorageError(
                        "controlled_file_staging_locator_invalid",
                        "staging 儲存邊界無效",
                        retryable=False,
                    )
                directory.mkdir(exist_ok=True)
            staging_root.resolve(strict=True).relative_to(root)
        except ControlledFileStorageError:
            raise
        except (OSError, ValueError) as error:
            raise ControlledFileStorageError(
                "controlled_file_staging_write_failed",
                "staging 檔案目前無法寫入",
                retryable=True,
            ) from error
        return staging_root

    def _create_staging_object_directory(self, staging_root: Path, staging_id: str) -> Path:
        identity = _validate_staging_id(staging_id)
        shard = staging_root / "objects" / identity[:2]
        try:
            if shard.is_symlink():
                raise ControlledFileStorageError(
                    "controlled_file_staging_locator_invalid",
                    "staging 儲存邊界無效",
                    retryable=False,
                )
            shard.mkdir(exist_ok=True)
            object_directory = shard / identity
            object_directory.mkdir()
            return object_directory
        except ControlledFileStorageError:
            raise
        except OSError as error:
            raise ControlledFileStorageError(
                "controlled_file_staging_write_failed",
                "staging 檔案目前無法寫入",
                retryable=True,
            ) from error

    def _staging_object_directory(self, root: Path, staging_id: str) -> Path:
        identity = _validate_staging_id(staging_id)
        staging_root = root / _STAGING_DIRECTORY
        candidate = staging_root / "objects" / identity[:2] / identity
        if any(path.is_symlink() for path in _path_chain(root, candidate)):
            raise ControlledFileStorageError(
                "controlled_file_staging_locator_invalid",
                "staging 儲存邊界無效",
                retryable=False,
            )
        return candidate

    def _read_staging_record(
        self,
        root: Path,
        staging_id: str,
        *,
        missing_ok: bool = False,
    ) -> tuple[dict[str, object], bytes]:
        object_directory = self._staging_object_directory(root, staging_id)
        metadata_path = object_directory / "metadata.json"
        payload_path = object_directory / "payload.bin"
        if payload_path.is_symlink() or metadata_path.is_symlink():
            raise ControlledFileStorageError(
                "controlled_file_staging_locator_invalid",
                "staging 儲存邊界無效",
                retryable=False,
            )
        try:
            metadata = _read_json(metadata_path)
            size_bytes = metadata.get("size_bytes")
            if metadata.get("staging_id") != staging_id or not isinstance(size_bytes, int):
                raise ValueError("invalid staging metadata")
            if size_bytes > self._max_staging_bytes:
                raise ControlledFileStorageError(
                    "controlled_file_staging_too_large",
                    "staging 檔案超過讀取上限",
                    retryable=False,
                )
            before = payload_path.stat()
            content = payload_path.read_bytes()
            after = payload_path.stat()
        except FileNotFoundError as error:
            if missing_ok:
                return {}, b""
            raise ControlledFileStorageError(
                "controlled_file_staging_not_found",
                "指定 staging 檔案不存在",
                retryable=False,
            ) from error
        except ControlledFileStorageError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ControlledFileStorageError(
                "controlled_file_staging_reconciliation_required",
                "staging 檔案狀態無法確認，需要對帳",
                retryable=False,
            ) from error
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ControlledFileStorageError(
                "controlled_file_staging_changed_during_read",
                "staging 檔案在讀取期間發生變更",
                retryable=True,
            )
        if before.st_size != size_bytes or len(content) != size_bytes:
            raise ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "staging 檔案完整性驗證失敗",
                retryable=False,
            )
        return metadata, content

    def _load_staging_result(
        self,
        root: Path,
        staging_id: str,
        *,
        replayed: bool,
    ) -> ControlledFileStagingResult:
        metadata, content = self._read_staging_record(root, staging_id)
        digest = hashlib.sha256(content).hexdigest()
        if digest != metadata.get("sha256_digest"):
            raise ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "staging 檔案完整性驗證失敗",
                retryable=False,
            )
        return _staging_result_from_metadata(metadata, replayed=replayed)

    @staticmethod
    def _remove_unindexed_candidate(object_directory: Path) -> None:
        for name in ("payload.bin", "metadata.json"):
            try:
                (object_directory / name).unlink()
            except FileNotFoundError:
                pass
        try:
            object_directory.rmdir()
        except (FileNotFoundError, OSError):
            pass

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
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)


def _validate_staging_input(
    *,
    idempotency_key: str,
    filename: str,
    mime_type: str,
    content: bytes,
    max_bytes: int,
) -> None:
    if (
        not isinstance(idempotency_key, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,190}", idempotency_key) is None
    ):
        raise ControlledFileStorageError(
            "controlled_file_staging_idempotency_invalid",
            "staging 重播識別格式無效",
            retryable=False,
        )
    if (
        not isinstance(filename, str)
        or not 1 <= len(filename) <= 255
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or any(ord(character) < 32 for character in filename)
    ):
        raise ControlledFileStorageError(
            "controlled_file_staging_filename_invalid",
            "staging 檔名格式無效",
            retryable=False,
        )
    if (
        not isinstance(mime_type, str)
        or not 3 <= len(mime_type) <= 255
        or mime_type.count("/") != 1
        or any(ord(character) < 33 or ord(character) > 126 for character in mime_type)
    ):
        raise ControlledFileStorageError(
            "controlled_file_staging_mime_invalid",
            "staging MIME 格式無效",
            retryable=False,
        )
    if not isinstance(content, bytes) or not content:
        raise ControlledFileStorageError(
            "controlled_file_staging_content_invalid",
            "staging 檔案內容必須為非空 bytes",
            retryable=False,
        )
    if len(content) > max_bytes:
        raise ControlledFileStorageError(
            "controlled_file_staging_too_large",
            "staging 檔案超過容量上限",
            retryable=False,
        )


def _validate_staging_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_STAGING_ID_PREFIX)
        or len(value) != len(_STAGING_ID_PREFIX) + 32
        or any(character not in "0123456789abcdef" for character in value[len(_STAGING_ID_PREFIX) :])
    ):
        raise ControlledFileStorageError(
            "controlled_file_staging_id_invalid",
            "staging identity 格式無效",
            retryable=False,
        )
    try:
        parsed = uuid.UUID(hex=value[len(_STAGING_ID_PREFIX) :])
    except ValueError as error:
        raise ControlledFileStorageError(
            "controlled_file_staging_id_invalid",
            "staging identity 格式無效",
            retryable=False,
        ) from error
    if parsed.version != 4:
        raise ControlledFileStorageError(
            "controlled_file_staging_id_invalid",
            "staging identity 格式無效",
            retryable=False,
        )
    return value


def _staging_fingerprint(
    *,
    filename: str,
    mime_type: str,
    size_bytes: int,
    sha256_digest: str,
) -> str:
    canonical = "\x00".join(
        ("controlled-file-staging.v1", filename, mime_type, str(size_bytes), sha256_digest)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_bytes_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def _parse_utc_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected datetime string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("expected timezone-aware datetime")
    return parsed.astimezone(timezone.utc)


def _staging_result_from_metadata(
    metadata: dict[str, object],
    *,
    replayed: bool,
) -> ControlledFileStagingResult:
    try:
        staging_id = _validate_staging_id(str(metadata["staging_id"]))
        filename = str(metadata["filename"])
        mime_type = str(metadata["mime_type"])
        size_bytes = int(metadata["size_bytes"])
        sha256_digest = str(metadata["sha256_digest"])
        expires_at = _parse_utc_datetime(metadata["expires_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ControlledFileStorageError(
            "controlled_file_staging_reconciliation_required",
            "staging 檔案狀態無法確認，需要對帳",
            retryable=False,
        ) from error
    if not _is_sha256(sha256_digest):
        raise ControlledFileStorageError(
            "controlled_file_staging_reconciliation_required",
            "staging 檔案狀態無法確認，需要對帳",
            retryable=False,
        )
    return ControlledFileStagingResult(
        staging_id=staging_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256_digest=sha256_digest,
        expires_at=expires_at,
        replayed=replayed,
    )


__all__ = ["FileSystemControlledFileStorage"]
