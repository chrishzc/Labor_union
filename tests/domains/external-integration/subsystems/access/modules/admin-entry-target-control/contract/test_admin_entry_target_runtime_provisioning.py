"""
File: test_admin_entry_target_runtime_provisioning.py
Description: 驗證 12-entry template 的 strict exclusive-create provisioning 契約。
"""

from pathlib import Path

import pytest

from infrastructure.file import admin_entry_target_store
from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from scripts.provision_admin_entry_target_state import provision_state
from subsystems.access.admin_entry_target_control import EntryTargetError, make_initial_state


ROOT = Path(__file__).resolve().parents[8]


def test_provision_requires_frozen_template_and_refuses_existing_target(tmp_path: Path) -> None:
    output = tmp_path / "state.json"
    receipt = provision_state(
        ROOT / "config/admin_entry_targets.initial.json", output, _allow_test_path=True
    )
    assert receipt["status"] == "ready"
    assert receipt["entry_count"] == 12
    assert receipt["receipt_count"] == 1
    assert output.exists()
    with pytest.raises(EntryTargetError, match="entry_target_destination_exists"):
        provision_state(ROOT / "config/admin_entry_targets.initial.json", output, _allow_test_path=True)


def test_provision_rejects_legacy_template_without_writing(tmp_path: Path) -> None:
    template = tmp_path / "legacy.json"
    template.write_text('{"schema_version": 1}', encoding="utf-8")
    output = tmp_path / "state.json"
    with pytest.raises(EntryTargetError, match="entry_target_template_invalid"):
        provision_state(template, output, _allow_test_path=True)
    assert not output.exists()


def test_provision_output_is_exact_initial_state(tmp_path: Path) -> None:
    output = tmp_path / "state.json"
    provision_state(ROOT / "config/admin_entry_targets.initial.json", output, _allow_test_path=True)
    state = FileAdminEntryTargetStore(output, _allow_test_path=True).read()
    assert state == make_initial_state()


def test_runtime_path_rejects_link_like_parent(monkeypatch, tmp_path: Path) -> None:
    parent = tmp_path / "durable"
    parent.mkdir()
    monkeypatch.setattr(
        admin_entry_target_store,
        "_is_link_like_path",
        lambda path: path == parent,
    )

    with pytest.raises(EntryTargetError, match="entry_target_path_invalid"):
        FileAdminEntryTargetStore(parent / "state.json", _allow_test_path=True)
