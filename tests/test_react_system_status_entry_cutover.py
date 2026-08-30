"""
File: test_react_system_status_entry_cutover.py
Description: 驗證 System Status identity 已進入 control plane genesis，但仍未執行 cutover。
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ROOT / "validation/scenarios/react_admin_entrypoints.json"
RETIREMENT_REQUIREMENTS = ROOT / "validation/scenarios/react_admin_retirement_requirements.json"
INITIAL_TARGETS = ROOT / "config/admin_entry_targets.initial.json"
REVIEW_QUEUE = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
)
SYSTEM_STATUS_ENTRY = "ui-react:#system-status"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_system_status_is_in_current_registry_and_retirement_set() -> None:
    entrypoint_registry = _read_json(ENTRYPOINTS)
    retirement_requirements = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = entrypoint_registry["react_entries"]
    retirement_entries = retirement_requirements["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    assert registry_entries.count(SYSTEM_STATUS_ENTRY) == 1
    assert retirement_entries.count(SYSTEM_STATUS_ENTRY) == 1


def test_system_status_queue_is_active_canonical_with_dedicated_witnesses() -> None:
    queue_entries = [entry for entry in _read_queue() if entry.get("entry_id") == SYSTEM_STATUS_ENTRY]

    assert len(queue_entries) == 1
    entry = queue_entries[0]
    assert entry["status"] == "active"
    assert entry["terminal_disposition"] == "active_canonical"
    assert entry["replacement"] == SYSTEM_STATUS_ENTRY
    assert entry["replacement_readback"] == f"current canonical entry readback: {SYSTEM_STATUS_ENTRY}"
    assert entry["streamlit_entry"] == "ui:08_system_status.py"
    assert entry["rollback_deep_link"] == "/?entry=system-status"
    assert entry["witnesses"] == {
        "nav": "ui_react/src/components/MasterLayout.tsx",
        "render": "ui_react/src/App.tsx",
    }

    assert entry["runtime_registration"] == "ui_react/src/components/MasterLayout.tsx::ui-react:#system-status"

    for relative_path in (
        "ui_react/src/App.tsx",
        "ui_react/src/components/MasterLayout.tsx",
        "ui_react/src/pages/SystemStatusPage.tsx",
        "ui_react/src/pages/SystemStatusPage.css",
        "ui_react/src/api/system/system_status_client.ts",
        "ui_react/src/tests/system_status_entry_identity.test.tsx",
    ):
        assert (ROOT / relative_path).is_file(), relative_path

    app_source = (ROOT / entry["witnesses"]["render"]).read_text(encoding="utf-8")
    assert "currentPage === 'system-status'" in app_source
    assert "<SystemStatusPage />" in app_source
    assert "SYSTEM_STATUS_ENTRY_IDENTITY" in (ROOT / "ui_react/src/pages/SystemStatusPage.tsx").read_text(
        encoding="utf-8"
    )


def test_system_status_control_plane_keeps_react_identity_metadata() -> None:
    initial_targets = _read_json(INITIAL_TARGETS)
    entries = initial_targets["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    system_status_entries = [entry for entry in entries if entry["entry_id"] == SYSTEM_STATUS_ENTRY]
    assert len(system_status_entries) == 1
    assert system_status_entries[0]["entry_id"] == SYSTEM_STATUS_ENTRY
    assert system_status_entries[0]["react_target"] == "/admin/#system-status"
    assert system_status_entries[0]["replacement_group"] == "reports-system"
