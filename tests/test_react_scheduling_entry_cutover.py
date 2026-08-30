"""
File: test_react_scheduling_entry_cutover.py
Description: 驗證 Scheduling entry 映射、Streamlit rollback 與 React 唯讀投影 client 邊界。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ROOT / "validation/scenarios/react_admin_entrypoints.json"
RETIREMENT_REQUIREMENTS = ROOT / "validation/scenarios/react_admin_retirement_requirements.json"
INITIAL_TARGETS = ROOT / "config/admin_entry_targets.initial.json"
REVIEW_QUEUE = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
)
SCHEDULING_ENTRY = "ui-react:#scheduling"
STAFF_ENTRY = "ui-react:#staff"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_scheduling_and_staff_registry_queue_and_rollback_mappings_are_consistent() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    for entry_id in (SCHEDULING_ENTRY, STAFF_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1

    assert registry["rollback_links"] == {
        **registry["rollback_links"],
        SCHEDULING_ENTRY: "/?entry=scheduling&view=calendar",
        STAFF_ENTRY: "/?entry=scheduling&view=staff-directory",
    }

    queue = _read_queue()
    expected = {
        SCHEDULING_ENTRY: {
            "streamlit_entry": "ui:03_calendar.py",
            "rollback_deep_link": "/?entry=scheduling&view=calendar",
        },
        STAFF_ENTRY: {
            "streamlit_entry": "ui:03_calendar.py",
            "rollback_deep_link": "/?entry=scheduling&view=staff-directory",
        },
    }
    for entry_id, expected_values in expected.items():
        entries = [entry for entry in queue if entry.get("entry_id") == entry_id]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["replacement"] == entry_id
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
        assert entry["replacement"] == entry_id


def test_scheduling_and_staff_control_plane_keep_react_identity_metadata() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    expected_targets = {SCHEDULING_ENTRY: "/admin/#scheduling", STAFF_ENTRY: "/admin/#staff"}
    for entry_id, expected_target in expected_targets.items():
        matches = [entry for entry in entries if entry["entry_id"] == entry_id]
        assert len(matches) == 1
        assert matches[0]["react_target"] == expected_target


def test_scheduling_projection_sources_are_typed_get_only() -> None:
    app_path = ROOT / "ui_react/src/App.tsx"
    nav_path = ROOT / "ui_react/src/components/MasterLayout.tsx"
    page_path = ROOT / "ui_react/src/pages/SchedulingPage.tsx"
    client_paths = (
        ROOT / "ui_react/src/api/staff_directory/staff_directory_client.ts",
        ROOT / "ui_react/src/api/scheduling/scheduling_current_client.ts",
    )

    app_source = app_path.read_text(encoding="utf-8")
    nav_source = nav_path.read_text(encoding="utf-8")
    page_source = page_path.read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'scheduling'\s*&&\s*<SchedulingPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{currentPage\s*===\s*'staff'\s*&&\s*<StaffPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'scheduling'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'staff'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "'scheduling': 'operations'" in nav_source
    assert "'staff': 'operations'" in nav_source

    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z_]+\b", page_source)
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\btransport\.(post|put|patch|delete)\b", page_source)

    for client_path in client_paths:
        client_source = client_path.read_text(encoding="utf-8")
        transport_methods = re.findall(
            r"\btransport\.(get|post|put|patch|delete)\b", client_source
        )
        assert transport_methods == ["get"], client_path
