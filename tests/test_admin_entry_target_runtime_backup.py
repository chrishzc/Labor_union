"""
File: test_admin_entry_target_runtime_backup.py
Description: 驗證 immutable backup 與只可 restore 至新路徑的 recovery 契約。
"""

from pathlib import Path

import pytest

from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from scripts.provision_admin_entry_target_state import (
    backup_state,
    provision_state,
    restore_state,
)
from subsystems.access.admin_entry_target_control import EntryTargetError


ROOT = Path(__file__).resolve().parents[1]


def _provision(tmp_path: Path) -> Path:
    output = tmp_path / "state.json"
    provision_state(ROOT / "config/admin_entry_targets.initial.json", output, _allow_test_path=True)
    return output


def test_backup_is_exclusive_and_restore_uses_new_path(tmp_path: Path) -> None:
    state_path = _provision(tmp_path)
    backup = tmp_path / "backup.json"
    restored = tmp_path / "restored.json"
    assert backup_state(state_path, backup, _allow_test_path=True)["entry_count"] == 12
    with pytest.raises(EntryTargetError, match="entry_target_destination_exists"):
        backup_state(state_path, backup, _allow_test_path=True)
    receipt = restore_state(backup, restored, _allow_test_path=True)
    assert receipt["state_digest"] == FileAdminEntryTargetStore(state_path, _allow_test_path=True).attest()["state_digest"]
    with pytest.raises(EntryTargetError, match="entry_target_restore_requires_new_path"):
        restore_state(backup, backup, _allow_test_path=True)


def test_backup_and_restore_preserve_exact_bytes(tmp_path: Path) -> None:
    state_path = _provision(tmp_path)
    backup = tmp_path / "backup.json"
    restored = tmp_path / "restored.json"
    backup_state(state_path, backup, _allow_test_path=True)
    restore_state(backup, restored, _allow_test_path=True)
    assert backup.read_bytes() == state_path.read_bytes() == restored.read_bytes()
