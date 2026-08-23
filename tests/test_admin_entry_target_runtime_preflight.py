"""
File: test_admin_entry_target_runtime_preflight.py
Description: 驗證 startup attestation 嚴格唯讀、去敏且拒絕 legacy 或毀損 state。
"""

from pathlib import Path

import pytest

from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from scripts.provision_admin_entry_target_state import provision_state
from subsystems.access.admin_entry_target_control import EntryTargetError


ROOT = Path(__file__).resolve().parents[1]


def _provision(tmp_path: Path) -> Path:
    output = tmp_path / "state.json"
    provision_state(ROOT / "config/admin_entry_targets.initial.json", output, _allow_test_path=True)
    return output


def test_attestation_is_zero_write_and_redacted(tmp_path: Path) -> None:
    state_path = _provision(tmp_path)
    store = FileAdminEntryTargetStore(state_path, _allow_test_path=True)
    before = {item.name for item in tmp_path.iterdir()}
    receipt = store.attest()
    after = {item.name for item in tmp_path.iterdir()}
    assert before == after == {"state.json"}
    assert receipt["status"] == "ready"
    assert receipt["entry_count"] == 12
    assert receipt["entry_ids"] == sorted(receipt["entry_ids"])
    assert not {"path", "username", "owner", "mtime", "token", "secret"} & set(receipt)


@pytest.mark.parametrize("mutator", [
    lambda payload: payload["entries"].pop(),
    lambda payload: payload["entries"].append(dict(payload["entries"][0])),
])
def test_attestation_rejects_non_exact_entry_set(tmp_path: Path, mutator) -> None:
    state_path = _provision(tmp_path)
    import json

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    mutator(payload)
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EntryTargetError):
        FileAdminEntryTargetStore(state_path, _allow_test_path=True).attest()
