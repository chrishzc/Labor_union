"""
File: test_react_data_import_entry_cutover.py
Description: 驗證Data Import entry目標、四種typed Preview／Apply接線與安全狀態說明。
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
DATA_IMPORT_ENTRY = "ui-react:#data-import"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_data_import_registry_queue_and_rollback_mapping_are_consistent() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    assert registry_entries.count(DATA_IMPORT_ENTRY) == 1
    assert retirement_entries.count(DATA_IMPORT_ENTRY) == 1
    assert registry["rollback_links"][DATA_IMPORT_ENTRY] == "/?entry=data-import"

    queue_entries = [entry for entry in _read_queue() if entry.get("entry_id") == DATA_IMPORT_ENTRY]
    assert len(queue_entries) == 1
    entry = queue_entries[0]
    assert entry["status"] == "review_required"
    assert entry["streamlit_entry"] == "ui:09_data_import.py"
    assert entry["rollback_deep_link"] == "/?entry=data-import"
    assert entry["witnesses"] == {
        "nav": "ui_react/src/components/MasterLayout.tsx",
        "render": "ui_react/src/App.tsx",
    }
    assert all(
        entry.get(field) in (None, False)
        for field in ("active", "replacement", "cutover_ready", "cutover-ready")
        if field in entry
    )

    api_entries = [
        entry
        for entry in _read_queue()
        if entry.get("entry_id") == "api:GET /api/v1/case-import/hcm/workbooks/results"
    ]
    assert len(api_entries) == 1
    assert api_entries[0]["status"] == "review_required"
    assert api_entries[0]["source_path"] == "api/routes/hcm_import.py"


def test_data_import_frozen_target_remains_streamlit_without_switch_receipts() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == len({entry["entry_id"] for entry in entries})
    data_import_entries = [entry for entry in entries if entry["entry_id"] == DATA_IMPORT_ENTRY]
    assert data_import_entries == [
        {
            "entry_id": DATA_IMPORT_ENTRY,
            "replacement_group": "data-import",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=data-import",
            "react_target": "/admin/#data-import",
            "required_react_artifact": None,
            "entry_revision": 1,
        }
    ]
    assert all(entry["current_target"] == "streamlit" for entry in entries)
    assert state["receipts"] == []


def test_data_import_sources_expose_typed_preview_apply_and_safety_guidance() -> None:
    app_path = ROOT / "ui_react/src/App.tsx"
    nav_path = ROOT / "ui_react/src/components/MasterLayout.tsx"
    page_path = ROOT / "ui_react/src/pages/DataImportPage.tsx"
    client_path = ROOT / "ui_react/src/api/case_import/hcm_import_result_client.ts"

    app_source = app_path.read_text(encoding="utf-8")
    nav_source = nav_path.read_text(encoding="utf-8")
    page_source = page_path.read_text(encoding="utf-8")
    client_source = client_path.read_text(encoding="utf-8")

    assert app_path.is_file()
    assert nav_path.is_file()
    assert page_path.is_file()
    assert client_path.is_file()
    assert re.search(
        r"\{currentPage\s*===\s*'data-import'\s*&&\s*<DataImportPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'data-import'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "imports.hcm-results.open" in page_source
    assert "imports.hcm-results.refresh" in page_source
    assert "hcmImportResultClient.query" in page_source

    assert "clientBeClassWorkbookPreviewClient.preview" in page_source
    assert "clientBeClassWorkbookPreviewClient.apply" in page_source
    assert "staffHistoricalWorkbookPreviewClient.preview" in page_source
    assert "staffHistoricalWorkbookPreviewClient.apply" in page_source
    assert "historicalOrderWorkbookPreviewClient.preview" in page_source
    assert "historicalOrderWorkbookPreviewClient.apply" in page_source
    assert "hcmWorkbookPreviewClient.preview" in page_source
    assert "hcmWorkbookPreviewClient.apply" in page_source
    assert "imports.hcm-current.preview" in page_source
    assert "imports.hcm-current.apply" in page_source
    assert "imports.${id}.preview" in page_source
    assert "imports.${id}.apply" in page_source
    assert "beforeunload" in page_source
    assert "Apply 結果尚未確認" in page_source
    assert "Receipt 已回傳，需檢查" in page_source
    assert "整份工作簿已重播／未新增寫入" in page_source
    assert "receipt.replayed_workbook" in page_source
    assert "imports.hcm-results.retry" in page_source
    assert "hcm-historical" not in page_source
    assert "bank-statements" not in page_source

    transport_methods = re.findall(
        r"\btransport\.(get|post|put|patch|delete)\b", client_source
    )
    assert transport_methods == ["get"]
    assert "/api/v1/case-import/hcm/workbooks/results" in client_source
    lowered_client_source = client_source.lower()
    assert "hcm_workbook_client" not in lowered_client_source
    assert "/preview" not in lowered_client_source
    assert "/apply" not in lowered_client_source
