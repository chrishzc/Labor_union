"""
File: admin_entry_target_store.py
Description: 以跨程序檔案鎖、fsync 與原子替換持久化管理端 entry target state。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from typing import TypeVar

from subsystems.access.admin_entry_target_control import (
    EntryTargetError,
    EntryTargetState,
    canonical_json_bytes,
    state_from_mapping,
    state_to_mapping,
)


T = TypeVar("T")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FileAdminEntryTargetStore:
    def __init__(self, state_path: Path, *, _allow_test_path: bool = False) -> None:
        self._enforce_location_policy = not _allow_test_path
        self._path = _validate_runtime_path(state_path, enforce_location_policy=self._enforce_location_policy)
        self._lock_path = self._path.with_name(f".{self._path.name}.lock")

    @property
    def state_path(self) -> Path:
        return self._path

    def read(self) -> EntryTargetState:
        with self._exclusive_lock():
            return self._read_unlocked()

    def attest(self) -> dict[str, object]:
        """Validate state without creating a lock, probe, or temporary file."""
        state = self._read_bytes_without_side_effects()
        return _redacted_attestation(state)

    def create(self, state: EntryTargetState) -> dict[str, object]:
        """Create a new state file exclusively and validate the exact readback."""
        _exclusive_write(
            self._path,
            canonical_json_bytes(state_to_mapping(state)) + b"\n",
        )
        return self.attest()

    def backup_to(self, backup_path: Path) -> dict[str, object]:
        state = self._read_bytes_without_side_effects()
        destination = _validate_runtime_path(backup_path, enforce_location_policy=self._enforce_location_policy)
        _exclusive_write(destination, canonical_json_bytes(state_to_mapping(state)) + b"\n")
        return _redacted_attestation(state)

    def restore_to(self, target_path: Path) -> dict[str, object]:
        state = self._read_bytes_without_side_effects()
        destination = _validate_runtime_path(target_path, enforce_location_policy=self._enforce_location_policy)
        if destination == self._path:
            raise EntryTargetError("validation", "entry_target_restore_requires_new_path", "Restore 必須寫入新路徑")
        _exclusive_write(destination, canonical_json_bytes(state_to_mapping(state)) + b"\n")
        return _redacted_attestation(state)

    def mutate(self, operation: Callable[[EntryTargetState], tuple[EntryTargetState, T]]) -> T:
        with self._exclusive_lock():
            current = self._read_unlocked()
            next_state, result = operation(current)
            if next_state != current:
                self._replace_unlocked(next_state)
                readback = self._read_unlocked()
                if readback != next_state:
                    raise EntryTargetError(
                        "unavailable",
                        "entry_target_state_readback_mismatch",
                        "Entry target state 寫入後驗證失敗",
                    )
            return result

    def _read_unlocked(self) -> EntryTargetState:
        try:
            raw = self._path.read_bytes()
        except (OSError, ValueError) as exc:
            raise EntryTargetError(
                "unavailable", "entry_target_state_unavailable", "Entry target state 無法讀取"
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EntryTargetError(
                "unavailable", "entry_target_state_corrupt", "Entry target state 已毀損"
            ) from exc
        return state_from_mapping(payload)

    def _read_bytes_without_side_effects(self) -> EntryTargetState:
        try:
            raw = self._path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EntryTargetError(
                "unavailable", "entry_target_state_unavailable", "Entry target state 無法讀取"
            ) from exc
        return state_from_mapping(payload)

    def _replace_unlocked(self, state: EntryTargetState) -> None:
        data = canonical_json_bytes(state_to_mapping(state)) + b"\n"
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                _write_all(handle, data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            temporary = None
            _fsync_directory(self._path.parent)
        except OSError as exc:
            raise EntryTargetError(
                "unavailable", "entry_target_state_write_failed", "Entry target state 寫入失敗"
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        try:
            with self._lock_path.open("a+b") as handle:
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                _lock(handle.fileno())
                try:
                    yield
                finally:
                    handle.seek(0)
                    _unlock(handle.fileno())
        except EntryTargetError:
            raise
        except (OSError, ImportError) as exc:
            raise EntryTargetError(
                "unavailable", "entry_target_lock_unavailable", "Entry target state lock 無法取得"
            ) from exc


def _validate_runtime_path(candidate: Path, *, enforce_location_policy: bool = True) -> Path:
    if not candidate.is_absolute():
        raise EntryTargetError("unavailable", "entry_target_path_invalid", "Entry target state path 必須是絕對路徑")
    if candidate.exists() and _is_link_like_path(candidate):
        raise EntryTargetError("unavailable", "entry_target_path_invalid", "Entry target state path 不得是 link-like path")
    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        raise EntryTargetError("unavailable", "entry_target_path_invalid", "Entry target state parent 不存在")
    for item in (parent, *parent.parents):
        if _is_link_like_path(item):
            raise EntryTargetError("unavailable", "entry_target_path_invalid", "Entry target state parent 不得是 link-like path")
    resolved = candidate.resolve(strict=False)
    forbidden_roots = {
        PROJECT_ROOT.resolve(),
        Path.cwd().resolve(),
        Path(tempfile.gettempdir()).resolve(),
        Path.home().resolve(),
    }
    if enforce_location_policy:
        for root in forbidden_roots:
            if resolved == root or root in resolved.parents:
                raise EntryTargetError(
                    "unavailable", "entry_target_path_forbidden", "Entry target state path 不得位於 source/cwd/temp"
                )
    return resolved


def _is_link_like_path(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _exclusive_write(destination: Path, data: bytes) -> None:
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            _write_all(handle, data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(destination.parent)
    except FileExistsError as exc:
        raise EntryTargetError("conflict", "entry_target_destination_exists", "Entry target destination 已存在") from exc
    except OSError as exc:
        raise EntryTargetError("unavailable", "entry_target_destination_write_failed", "Entry target destination 寫入失敗") from exc


def _redacted_attestation(state: EntryTargetState) -> dict[str, object]:
    return {
        "status": "ready",
        "schema_version": state.schema_version,
        "registry_revision": state.registry_revision,
        "registry_digest": state.registry_digest,
        "revision": state.revision,
        "state_digest": state.state_digest,
        "entry_count": len(state.entries),
        "receipt_count": len(state.receipts),
        "entry_ids": [item.entry_id for item in state.entries],
    }


def _lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        return
    if os.name == "posix":
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return
    raise EntryTargetError("unavailable", "entry_target_lock_unsupported", "目前平台不支援 entry target lock")


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    if os.name == "posix":
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(handle, data: bytes) -> None:
    written = 0
    while written < len(data):
        count = handle.write(data[written:])
        if not isinstance(count, int) or count <= 0:
            raise OSError("entry target state short write")
        written += count
