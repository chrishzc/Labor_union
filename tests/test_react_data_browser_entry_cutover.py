"""
File: test_react_data_browser_entry_cutover.py
Description: 驗證 Data Browser entry 的 registry、Streamlit rollback 與 React 唯讀接線見證。
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
DATA_BROWSER_ENTRY = "ui-react:#data-browser"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_data_browser_registry_alias_has_current_rollback_mapping_without_fake_runtime_entry() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    assert registry_entries.count(DATA_BROWSER_ENTRY) == 1
    assert retirement_entries.count(DATA_BROWSER_ENTRY) == 1
    assert registry["rollback_links"][DATA_BROWSER_ENTRY] == "/?entry=data-browser"

    queue_entries = [
        entry for entry in _read_queue() if entry.get("entry_id") == DATA_BROWSER_ENTRY
    ]
    # The successor keeps the hash only as a deterministic deep-link alias.
    # It must not be reintroduced into the exact runtime queue as a separate
    # navigation entry now that Data Import owns the rendered composition.
    assert queue_entries == []
    successor = [
        entry for entry in _read_queue() if entry.get("entry_id") == "ui-react:#data-import"
    ]
    assert len(successor) == 1
    assert successor[0]["status"] == "active"
    assert successor[0]["terminal_disposition"] == "active_canonical"


def test_data_browser_frozen_control_plane_remains_streamlit_without_receipt() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    data_browser_entries = [
        entry for entry in entries if entry["entry_id"] == DATA_BROWSER_ENTRY
    ]
    assert data_browser_entries == [
        {
            "entry_id": DATA_BROWSER_ENTRY,
            "replacement_group": "data-browser",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=data-browser",
            "react_target": "/admin/#data-browser",
            "required_react_artifact": None,
            "entry_revision": 1,
        }
    ]
    assert all(
        entry["current_target"] == ("react" if entry["entry_id"] == "ui-react:#anomalies" else "streamlit")
        for entry in entries
    )
    assert len(state["receipts"]) == 1
    assert state["receipts"][0]["entry_id"] == "ui-react:#anomalies"


def test_data_browser_app_nav_and_bounded_client_remain_query_only() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(
        encoding="utf-8"
    )
    page_source = (ROOT / "ui_react/src/pages/DataBrowserPage.tsx").read_text(
        encoding="utf-8"
    )
    adapter_source = (
        ROOT / "ui_react/src/adapters/data_browser/data_browser_query_adapter.ts"
    ).read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'data-browser'\s*&&\s*"
        r"<DataImportPage\s+initialTab=\"data-browser\"\s*/>\}",
        app_source,
    )
    assert "const sidebarCurrentPage = currentPage === 'data-browser' ? 'data-import'" in nav_source
    assert not re.search(r"\{\s*id:\s*'data-browser'\s*,", nav_source)
    for source_id in (
        "orders",
        "clients",
        "staff",
        "beclass_intake",
        "hcm_review",
        "bank_facts",
    ):
        assert f"sourceId: '{source_id}'" in adapter_source

    for control_id in (
        "data-browser.patch",
        "data-browser.source-correction.preview",
        "data-browser.source-correction.apply",
    ):
        assert f'data-control-id="{control_id}"' not in page_source

    client_path = ROOT / "ui_react/src/api/data_browser/data_browser_query_client.ts"
    client_source = client_path.read_text(encoding="utf-8")
    methods = re.findall(r"\btransport\.(get|post|put|patch|delete)\b", client_source)
    assert methods == ["get"]
    assert "transport.post" not in client_source
    assert "transport.patch" not in client_source
