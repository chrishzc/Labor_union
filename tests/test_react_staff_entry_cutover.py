"""
File: test_react_staff_entry_cutover.py
Description: 驗證 Staff entry 治理映射、typed action client 安全鏈與 unavailable 控件。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ROOT / "validation/scenarios/react_admin_entrypoints.json"
RETIREMENT_REQUIREMENTS = (
    ROOT / "validation/scenarios/react_admin_retirement_requirements.json"
)
ENTRY_QUEUE = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
)
CONTROL_PLANE = ROOT / "config/admin_entry_targets.initial.json"
APP = ROOT / "ui_react/src/App.tsx"
MASTER_LAYOUT = ROOT / "ui_react/src/components/MasterLayout.tsx"
STAFF_PAGE = ROOT / "ui_react/src/pages/StaffPage.tsx"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _entries(payload: dict[str, Any]) -> list[str]:
    entries = payload.get("react_entries")
    assert isinstance(entries, list)
    return entries


def _queue_rows() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in ENTRY_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_staff_entry_registry_queue_and_rollback_are_independent() -> None:
    registry_payload = _json(ENTRYPOINTS)
    registry = _entries(registry_payload)
    retirement = _entries(_json(RETIREMENT_REQUIREMENTS))

    assert len(registry) == 15
    assert len(set(registry)) == 15
    assert set(registry) == set(retirement)
    assert registry.count("ui-react:#staff") == 1
    assert registry_payload["rollback_links"]["ui-react:#staff"] == (
        "/?entry=scheduling&view=staff-directory"
    )

    queued = [row for row in _queue_rows() if row.get("entry_id") == "ui-react:#staff"]
    assert len(queued) == 1
    row = queued[0]
    assert row["replacement_group"] == "staff-scheduling"
    assert row["status"] == "active"
    assert row["terminal_disposition"] == "active_canonical"
    assert row["replacement"] == "ui-react:#staff"
    assert row["streamlit_entry"] == "ui:03_calendar.py"
    assert row["rollback_deep_link"] == "/?entry=scheduling&view=staff-directory"
    assert row["witnesses"] == {
        "nav": "ui_react/src/components/MasterLayout.tsx",
        "render": "ui_react/src/App.tsx",
    }
    assert row["source_path"] == "ui_react/src/components/MasterLayout.tsx"


def test_staff_control_plane_keeps_react_identity_metadata() -> None:
    control = _json(CONTROL_PLANE)
    targets = control.get("entry_targets", control.get("entries"))
    assert isinstance(targets, list)
    assert len(targets) == 12

    staff_targets = [
        target for target in targets if target.get("entry_id") == "ui-react:#staff"
    ]
    assert len(staff_targets) == 1
    assert staff_targets[0]["entry_id"] == "ui-react:#staff"
    assert staff_targets[0]["react_target"] == "/admin/#staff"
    assert staff_targets[0]["replacement_group"] == "staff-scheduling"


def test_staff_app_page_and_clients_are_typed_and_fail_closed() -> None:
    app = APP.read_text(encoding="utf-8")
    layout = MASTER_LAYOUT.read_text(encoding="utf-8")
    page = STAFF_PAGE.read_text(encoding="utf-8")

    assert "from './pages/StaffPage'" in app
    assert "currentPage === 'staff' && <StaffPage />" in app
    assert re.search(r"id:\s*'staff'[^\n]+section:\s*'operations'", layout)
    assert re.search(r"['\"]staff['\"]\s*:\s*['\"]operations['\"]", layout)

    assert "mockData" not in page
    assert not re.search(r"\bMOCK_[A-Z0-9_]+\b", page)
    assert not re.search(r"\bfetch\s*\(", page)
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", page)
    assert "staffDirectoryClient.queryPage" in page
    assert "STAFF_DIRECTORY_UNAVAILABLE" not in page
    assert "data-control-id=\"staff.preferences.preview\"" in page
    assert "data-control-id=\"staff.preferences.apply\"" in page
    assert "data-control-id=\"staff.availability.create.preview\"" in page
    assert "data-control-id=\"staff.availability.create.apply\"" in page
    assert "data-control-id=\"staff.availability.end-pause\"" in page

    client_paths = {
        "directory": ROOT / "ui_react/src/api/staff_directory/staff_directory_client.ts",
        "preferences": ROOT
        / "ui_react/src/api/staff_preferences/staff_preferences_client.ts",
        "availability": ROOT
        / "ui_react/src/api/staff_availability/staff_availability_client.ts",
        "lifecycle": ROOT / "ui_react/src/api/staff_lifecycle/staff_lifecycle_client.ts",
    }
    expected_methods = {
        "directory": ["get"],
        "preferences": ["get", "get", "post", "post"],
        "availability": ["get", "post", "post"],
        "lifecycle": ["get", "post", "post"],
    }
    for name, path in client_paths.items():
        source = path.read_text(encoding="utf-8")
        methods = re.findall(r"\btransport\.(get|post|put|patch|delete)\b", source)
        assert methods == expected_methods[name]
        if name == "directory":
            assert "preview" not in source
            assert "apply" not in source
            continue
        assert "/preview" in source
        assert "/apply" in source
        assert "transport.post" in source
        assert "idempotencyKey: string" in source
        assert "Idempotency-Key" in source

    for marker in (
        "staffPreferencesClient.previewProfile",
        "staffPreferencesClient.applyProfile",
        "staffAvailabilityClient.previewChange",
        "staffAvailabilityClient.applyChange",
        "staffLifecycleClient.preview",
        "staffLifecycleClient.apply",
    ):
        assert marker in page
    assert page.count("preview_fingerprint: preview.preview_fingerprint") >= 3
    assert "expected_version" in page
    assert "nextIntentKey" in page
    assert page.count("phase !== 'preview_ready'") >= 3
