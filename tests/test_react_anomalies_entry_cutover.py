"""
File: test_react_anomalies_entry_cutover.py
Description: 驗證 Anomalies current entry 的 registry、navigation、唯讀 Query 與 owner action descriptor 邊界。
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
ANOMALIES_ENTRY = "ui-react:#anomalies"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_anomalies_is_unique_in_current_registries_and_review_queue() -> None:
    entrypoint_registry = _read_json(ENTRYPOINTS)
    retirement_requirements = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = entrypoint_registry["react_entries"]
    retirement_entries = retirement_requirements["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    assert registry_entries.count(ANOMALIES_ENTRY) == 1
    assert retirement_entries.count(ANOMALIES_ENTRY) == 1
    assert entrypoint_registry["rollback_links"][ANOMALIES_ENTRY] == "/?entry=anomalies"

    queue_entries = [entry for entry in _read_queue() if entry.get("entry_id") == ANOMALIES_ENTRY]
    assert len(queue_entries) == 1
    queue_entry = queue_entries[0]
    assert queue_entry["status"] == "active"
    assert queue_entry["terminal_disposition"] == "active_canonical"
    assert queue_entry["replacement"] == ANOMALIES_ENTRY
    assert queue_entry["replacement_readback"] == f"current canonical entry readback: {ANOMALIES_ENTRY}"
    assert queue_entry["streamlit_entry"] == "ui:06_finance_alerts.py"
    assert queue_entry["rollback_deep_link"] == "/?entry=anomalies"
    assert queue_entry["witnesses"] == {
        "nav": "ui_react/src/components/MasterLayout.tsx",
        "render": "ui_react/src/App.tsx",
    }
    assert queue_entry["runtime_registration"].startswith(
        "ui_react/src/components/MasterLayout.tsx::"
    )


def test_anomalies_control_plane_keeps_react_identity_metadata() -> None:
    initial_targets = _read_json(INITIAL_TARGETS)
    entries = initial_targets["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    anomalies_entries = [entry for entry in entries if entry["entry_id"] == ANOMALIES_ENTRY]
    assert len(anomalies_entries) == 1
    assert anomalies_entries[0]["entry_id"] == ANOMALIES_ENTRY
    assert anomalies_entries[0]["react_target"] == "/admin/#anomalies"
    assert anomalies_entries[0]["replacement_group"] == "anomalies"


def test_anomalies_sources_use_current_read_only_owner_boundaries() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(encoding="utf-8")
    page_source = (ROOT / "ui_react/src/pages/CurrentAnomaliesPage.tsx").read_text(
        encoding="utf-8"
    )
    current_query_client_source = (
        ROOT / "ui_react/src/api/anomalies/current_anomaly_query_client.ts"
    ).read_text(encoding="utf-8")
    detail_client_source = (
        ROOT / "ui_react/src/api/anomalies/anomaly_detail_client.ts"
    ).read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'anomalies'\s*&&\s*<CurrentAnomaliesPage\s*/>\}",
        app_source,
    )
    assert re.search(r"\{\s*id:\s*'anomalies'\s*,[^}]*section:\s*'audit'\s*\}", nav_source)

    assert "currentAnomalyQueryClient.queryCurrentAnomalies" in page_source
    assert "anomalyDetailClient.queryCurrentAnomalyRecovery" in page_source
    assert "detail.available_actions" in page_source
    assert "action.preview_operation" in page_source
    assert "action.apply_operation" in page_source
    assert "action.completion_predicate" in page_source
    assert "系統不會用通用結案取代業務修正" in page_source

    for retired_path in (
        "importWarningTransitionClient",
        "financeImportCorrectionClient",
        "queryAnomalyDetail",
        "anomalies.import-warning.transition.apply",
        "anomalies.finance-correction.apply",
    ):
        assert retired_path not in page_source

    assert re.findall(
        r"\btransport\.(get|post|put|patch|delete)\b",
        current_query_client_source,
    ) == ["get"]
    assert re.findall(
        r"\btransport\.(get|post|put|patch|delete)\b",
        detail_client_source,
    ) == ["get"]
