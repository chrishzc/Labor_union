"""
File: test_admin_entry_target_store.py
Description: 驗證 entry target store 的 strict read、原子 replace、readback 與毀損 fail-closed。
"""

from dataclasses import replace
from pathlib import Path
from threading import Event, Lock, Thread

import pytest

import infrastructure.file.admin_entry_target_store as store_module
from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from subsystems.access.admin_entry_target_control import (
    AdminEntryTargetControl,
    ArtifactBinding,
    ArtifactHealth,
    EntryTargetError,
    SwitchCommand,
    canonical_json_bytes,
    calculate_state_digest,
    make_initial_state,
    state_to_mapping,
)


def allowed_store(tmp_path: Path, monkeypatch) -> FileAdminEntryTargetStore:
    monkeypatch.setattr(store_module, "PROJECT_ROOT", tmp_path.parent / "unrelated-source")
    monkeypatch.setattr(store_module.tempfile, "gettempdir", lambda: str(tmp_path.parent / "unrelated-temp"))
    path = tmp_path / "entry-targets.json"
    path.write_bytes(canonical_json_bytes(state_to_mapping(make_initial_state())) + b"\n")
    return FileAdminEntryTargetStore(path, _allow_test_path=True)


def test_store_mutation_is_atomic_and_readback_validated(tmp_path: Path, monkeypatch) -> None:
    store = allowed_store(tmp_path, monkeypatch)
    lock_events = []
    original_lock = store_module._lock
    original_unlock = store_module._unlock
    monkeypatch.setattr(store_module, "_lock", lambda descriptor: (lock_events.append("lock"), original_lock(descriptor))[1])
    monkeypatch.setattr(store_module, "_unlock", lambda descriptor: (lock_events.append("unlock"), original_unlock(descriptor))[1])

    artifact = ArtifactBinding("react-v1", "a" * 64, "api-v1")

    class HealthyArtifact:
        def query(self):
            return ArtifactHealth(True, artifact.version, artifact.digest, artifact.api_compatibility_revision)

    receipt = AdminEntryTargetControl(store, HealthyArtifact()).apply(
        SwitchCommand(
            "ui-react:#orders",
            2,
            1,
            "streamlit",
            "react",
            artifact,
            "activate_react",
            "store-switch-1",
            "admin:1",
            "correlation-1",
        )
    )

    assert receipt.resulting_state_revision == 3
    assert store.read().revision == 3
    assert not list(tmp_path.glob("*.tmp"))
    assert lock_events == ["lock", "unlock", "lock", "unlock"]


@pytest.mark.parametrize("content", [b"not-json", b"{}", b'{"schema_version":1}'])
def test_store_never_bootstraps_missing_or_corrupt_state(tmp_path: Path, monkeypatch, content: bytes) -> None:
    store = allowed_store(tmp_path, monkeypatch)
    store.state_path.write_bytes(content)

    with pytest.raises(EntryTargetError):
        store.read()


def test_store_never_recreates_missing_state(tmp_path: Path, monkeypatch) -> None:
    store = allowed_store(tmp_path, monkeypatch)
    store.state_path.unlink()

    with pytest.raises(EntryTargetError, match="entry_target_state_unavailable"):
        store.read()
    assert not store.state_path.exists()


def test_store_rejects_legacy_eleven_entry_state(tmp_path: Path, monkeypatch) -> None:
    store = allowed_store(tmp_path, monkeypatch)
    initial = make_initial_state()
    legacy = replace(
        initial,
        registry_revision="phase5a-mapped-entries-v1",
        registry_digest="31de811259c9e737c5c136e85a4190fbeaa2278d67d83c396f2b55a62548a1ce",
        entries=tuple(item for item in initial.entries if item.entry_id != "ui-react:#system-status"),
        state_digest="",
    )
    legacy = replace(legacy, state_digest=calculate_state_digest(legacy))
    store.state_path.write_bytes(canonical_json_bytes(state_to_mapping(legacy)) + b"\n")

    with pytest.raises(EntryTargetError, match="entry_target_registry_stale"):
        store.read()


def test_store_rejects_relative_source_and_temp_paths(tmp_path: Path) -> None:
    with pytest.raises(EntryTargetError, match="entry_target_path_invalid"):
        FileAdminEntryTargetStore(Path("relative.json"))
    with pytest.raises(EntryTargetError, match="entry_target_path_forbidden"):
        FileAdminEntryTargetStore(Path.cwd() / "entry-targets.json")
    with pytest.raises(EntryTargetError, match="entry_target_path_forbidden"):
        FileAdminEntryTargetStore(tmp_path / "entry-targets.json")


def test_atomic_replace_failure_returns_no_receipt_and_preserves_state(tmp_path: Path, monkeypatch) -> None:
    store = allowed_store(tmp_path, monkeypatch)
    artifact = ArtifactBinding("react-v1", "a" * 64, "api-v1")

    class HealthyArtifact:
        def query(self):
            return ArtifactHealth(True, artifact.version, artifact.digest, artifact.api_compatibility_revision)

    original_replace = store_module.os.replace
    monkeypatch.setattr(store_module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(EntryTargetError, match="entry_target_state_write_failed"):
        AdminEntryTargetControl(store, HealthyArtifact()).apply(
            SwitchCommand(
                "ui-react:#orders", 2, 1, "streamlit", "react", artifact,
                "activate_react", "store-switch-fail", "admin:1", "correlation-1",
            )
        )
    monkeypatch.setattr(store_module.os, "replace", original_replace)

    assert store.read().revision == 2
    assert len(store.read().receipts) == 1


def test_concurrent_reads_share_one_exclusive_critical_section(tmp_path: Path, monkeypatch) -> None:
    first = allowed_store(tmp_path, monkeypatch)
    second = FileAdminEntryTargetStore(first.state_path, _allow_test_path=True)
    shared_lock = Lock()
    first_entered = Event()
    release_first = Event()
    second_completed = Event()
    original_first_read = first._read_unlocked

    monkeypatch.setattr(store_module, "_lock", lambda _descriptor: shared_lock.acquire())
    monkeypatch.setattr(store_module, "_unlock", lambda _descriptor: shared_lock.release())

    def blocked_read():
        first_entered.set()
        assert release_first.wait(timeout=2)
        return original_first_read()

    monkeypatch.setattr(first, "_read_unlocked", blocked_read)
    first_thread = Thread(target=first.read)
    second_thread = Thread(target=lambda: (second.read(), second_completed.set()))
    first_thread.start()
    assert first_entered.wait(timeout=2)
    second_thread.start()
    assert not second_completed.wait(timeout=0.05)
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert second_completed.is_set()


def test_write_all_retries_partial_writes_and_fails_closed_on_zero_progress() -> None:
    class PartialWriter:
        def __init__(self):
            self.payload = bytearray()

        def write(self, data):
            count = min(2, len(data))
            self.payload.extend(data[:count])
            return count

    writer = PartialWriter()
    store_module._write_all(writer, b"abcdef")
    assert bytes(writer.payload) == b"abcdef"

    class StalledWriter:
        def write(self, _data):
            return 0

    with pytest.raises(OSError, match="short write"):
        store_module._write_all(StalledWriter(), b"x")
