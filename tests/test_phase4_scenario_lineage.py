"""
File: test_phase4_scenario_lineage.py
Description: 驗證完整 Phase 4 lineage、15 筆 coverage 與 metadata-only receipt 的 fail-closed 契約。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.verification_gate_report import build_gate_report


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "validation/catalog/phase4_scenario_lineage.json"
RECEIPT_PATH = ROOT / "validation/receipts/phase4/manifest.json"

EXPECTED_SCENARIOS = {
    "LINE-REACT-DELIVERY-QUERY-001",
    "KN-REACT-CATALOG-QUERY-001",
    "KN-REACT-LIFECYCLE-001",
    "LINE-RICH-MENU-PUBLICATION-001",
    "LINE-NOTIFICATION-RULE-001",
    "JOB-PUBLIC-OUTCOME-001",
}
EXPECTED_COVERAGE = {
    "PH4-HCM-APPLY",
    "PH4-BECLASS-WORKBOOK",
    "PH4-STAFF-HISTORICAL-WORKBOOK",
    "PH4-HISTORICAL-ORDERS-WORKBOOK",
    "PH4-FINANCE-IMPORT",
    "PH4-ACCOUNTS-PAYABLE",
    "PH4-CLIENT-FINANCE",
    "PH4-STAFF-PAYOUT",
    "PH4-GOVERNMENT-SUBSIDY-REPORT",
    "PH4-LINE-DELIVERY-QUERY",
    "PH4-KNOWLEDGE-CATALOG-QUERY",
    "PH4-KNOWLEDGE-LIFECYCLE",
    "PH4-RICH-MENU-PUBLICATION",
    "PH4-NOTIFICATION-RULE-MUTATION",
    "PH4-DURABLE-JOB-OUTCOME",
}
ALLOWED_DISPOSITIONS = {"UNCHANGED", "RENAMED", "SUPPLEMENT", "TEST_DATA_GAP"}
ALLOWED_LINEAGE = {"unchanged", "renamed", "regenerated", "superseded", "unresolved"}
ALLOWED_DEPENDENCIES = {
    "hard-dependency",
    "soft-dependency",
    "global-dependency",
    "independent-lane",
}
INITIAL_RECEIPT_STATES = {"missing", "not_run", "blocked"}


def test_phase4_metadata_scenarios_do_not_enter_baseline_runtime_fixture_gate() -> None:
    report = build_gate_report()

    fixture_errors = report["errors"]["fixtures"]
    assert all(scenario_id not in " ".join(fixture_errors) for scenario_id in EXPECTED_SCENARIOS)


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM is forbidden: {path}"
    parsed = json.loads(raw.decode("utf-8"))
    assert isinstance(parsed, dict), f"root must be an object: {path}"
    return parsed


def _resolve(relative_path: str) -> Path:
    target = (ROOT / relative_path).resolve()
    assert target.is_relative_to(ROOT), f"path escapes repository: {relative_path}"
    return target


def _catalog() -> dict[str, Any]:
    return _load_json(CATALOG_PATH)


def _entry_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = catalog["entries"]
    result = {entry["scenario_id"]: entry for entry in entries}
    assert len(result) == len(entries), "duplicate scenario_id"
    return result


def _assert_anchor(source_ref: str) -> None:
    path_text, separator, anchor = source_ref.partition("#")
    source_path = _resolve(path_text)
    assert source_path.is_file(), source_ref
    if separator:
        assert anchor in source_path.read_text(encoding="utf-8"), source_ref


def _assert_acyclic(entries: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(scenario_id: str) -> None:
        if scenario_id in visiting:
            pytest.fail(f"dependency cycle at {scenario_id}")
        if scenario_id in visited:
            return
        visiting.add(scenario_id)
        for dependency in entries[scenario_id]["dependencies"]:
            assert dependency["type"] in ALLOWED_DEPENDENCIES
            target = dependency["scenario_id"]
            assert target in entries, f"dangling dependency: {target}"
            if dependency["type"] == "hard-dependency":
                visit(target)
        visiting.remove(scenario_id)
        visited.add(scenario_id)

    for identity in entries:
        visit(identity)


def _validate_catalog(catalog: dict[str, Any]) -> None:
    assert catalog["contract"] == "labor-union-phase4-scenario-lineage/v1"
    assert catalog["catalog_status"] == "metadata-ready"
    assert catalog["completion_output"] == "PHASE4_SCENARIO_LINEAGE_METADATA_READY"
    assert catalog["runtime_status"] == "not_run"
    assert set(catalog["authorized_scope"]) == EXPECTED_COVERAGE
    assert len(catalog["authorized_scope"]) == len(EXPECTED_COVERAGE)
    assert set(catalog["expected_scenario_ids"]) == EXPECTED_SCENARIOS
    assert len(catalog["expected_scenario_ids"]) == len(EXPECTED_SCENARIOS)
    entries = _entry_map(catalog)
    assert set(entries) == EXPECTED_SCENARIOS
    _assert_acyclic(entries)

    coverage = catalog["coverage_records"]
    coverage_ids = [record["coverage_id"] for record in coverage]
    assert set(coverage_ids) == EXPECTED_COVERAGE
    assert len(coverage_ids) == len(set(coverage_ids)) == len(EXPECTED_COVERAGE)
    assert len({record["receipt_id"] for record in coverage}) == len(coverage)


def test_catalog_declares_complete_metadata_only_scope() -> None:
    _validate_catalog(_catalog())


def test_successor_scenarios_have_traceable_sources_and_artifacts() -> None:
    catalog = _catalog()
    for entry in catalog["entries"]:
        assert entry["successor_scenario_id"] == entry["scenario_id"]
        assert entry["revision"] >= 1
        assert entry["owner"] and entry["business_now"] and entry["command_lineage"]
        assert entry["disposition"] in ALLOWED_DISPOSITIONS
        assert entry["activation_blockers"] and entry["missing_artifacts"]
        assert entry["pii_classification"] == "synthetic"
        for source_ref in entry["source_refs"]:
            _assert_anchor(source_ref)

        source_ids = entry["source_scenario_ids"]
        if source_ids:
            assert "source_scenario_absence_reason" not in entry
            for source_id in source_ids:
                assert (_resolve(f"validation/scenarios/{source_id}.json")).is_file()
        else:
            assert entry["scenario_id"] in {
                "LINE-RICH-MENU-PUBLICATION-001",
                "LINE-NOTIFICATION-RULE-001",
            }
            assert entry["source_scenario_absence_reason"] == "no canonical scenario exists"

        dispositions = {mapping["disposition"] for mapping in entry["lineage_mappings"]}
        assert dispositions <= ALLOWED_LINEAGE
        assert dispositions
        artifact_paths = [entry["scenario_path"], *entry["fixture_paths"], *entry["expected_paths"]]
        assert set(entry["artifact_digests"]) == set(artifact_paths)
        for relative_path in artifact_paths:
            artifact = _resolve(relative_path)
            assert artifact.is_file(), relative_path
            assert _load_json(artifact)
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            assert entry["artifact_digests"][relative_path] == digest


def test_browser_and_oracle_contracts_fail_closed() -> None:
    for entry in _catalog()["entries"]:
        assert set(entry["oracle_applicability"]) == {"db", "api", "ui", "replay", "recovery"}
        assert set(entry["oracle_applicability"].values()) <= {"required", "blocked", "not_applicable"}
        assert entry["browser_checklist_step_ids"] == []
        if entry["browser_execution_mode"] == "not-applicable":
            assert entry["scenario_id"] == "JOB-PUBLIC-OUTCOME-001"
            assert entry["browser_checklist_path"] is None
        else:
            assert entry["browser_execution_mode"] == "browser-blocked"
            assert "browser" in " ".join(entry["missing_artifacts"]).lower()
            checklist = _resolve(entry["browser_checklist_path"])
            if not checklist.is_file():
                assert "checklist" in " ".join(entry["missing_artifacts"]).lower()


def test_coverage_records_are_artifact_complete_but_runtime_blocked() -> None:
    catalog = _catalog()
    for record in catalog["coverage_records"]:
        assert record["disposition"] in ALLOWED_DISPOSITIONS
        assert record["runtime_receipt_status"] in INITIAL_RECEIPT_STATES
        assert record["browser_status"] in {"blocked", "not_applicable"}
        assert record["activation_status"] == "blocked"
        assert record["activation_blockers"]
        assert record["browser_checklist_step_ids"] == []
        for relative_path in [record["scenario_path"], *record["fixture_paths"], *record["expected_paths"]]:
            assert _resolve(relative_path).is_file(), relative_path
            assert _load_json(_resolve(relative_path))
        if record["browser_status"] == "not_applicable":
            assert record["coverage_id"] == "PH4-DURABLE-JOB-OUTCOME"
            assert record["browser_checklist_path"] is None
        else:
            checklist = _resolve(record["browser_checklist_path"])
            if not checklist.is_file():
                assert record["browser_status"] == "blocked"


def test_durable_job_fixture_does_not_seed_a_terminal_success() -> None:
    fixture = _load_json(ROOT / "validation/fixtures/phase4/durable_job_public_outcome.json")
    assert fixture["input_values"]["initial_queue_state"] == "accepted"
    assert "terminal_outcome" not in fixture["input_values"]
    assert "terminal_outcome" not in fixture["seed_fields"]
    assert "masked_public_outcome" in fixture["derived_fields"]


def test_receipt_registry_matches_coverage_without_runtime_results() -> None:
    catalog = _catalog()
    registry = _load_json(RECEIPT_PATH)
    assert registry["contract"] == "labor-union-validation-receipt-registry/v1"
    assert registry["scope_contract"] == catalog["contract"]
    assert registry["registry_status"] == "metadata-ready"
    assert set(registry["authorized_scope"]) == EXPECTED_COVERAGE
    assert set(registry["allowed_initial_states"]) == INITIAL_RECEIPT_STATES
    assert set(registry["execution_limits"].values()) == {"not_run"}
    receipt_rows = registry["receipts"]
    assert len(receipt_rows) == len(EXPECTED_COVERAGE)
    assert len({row["receipt_id"] for row in receipt_rows}) == len(receipt_rows)
    actual = {(row["coverage_id"], row["scenario_id"], row["receipt_id"]) for row in receipt_rows}
    expected = {(row["coverage_id"], row["scenario_id"], row["receipt_id"]) for row in catalog["coverage_records"]}
    assert actual == expected
    for row in receipt_rows:
        assert row["status"] in INITIAL_RECEIPT_STATES
        assert row["blocked_reason"]
        assert not ({"result", "runtime_result", "passed_at", "completed_at"} & set(row))


def test_metadata_cannot_be_misrepresented_as_runtime_pass() -> None:
    documents = [_catalog(), _load_json(RECEIPT_PATH)]
    forbidden_values = {"pass", "passed", "success", "succeeded", "complete", "completed", "ready"}

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and key in {"runtime_status", "runtime_receipt_status", "status", "activation_status"}:
            assert value.lower() not in forbidden_values

    for document in documents:
        walk(document)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_expected_scenario_identity_drift_is_rejected(mutation: str) -> None:
    catalog = copy.deepcopy(_catalog())
    if mutation == "missing":
        catalog["entries"].pop()
    elif mutation == "extra":
        extra = copy.deepcopy(catalog["entries"][0])
        extra["scenario_id"] = extra["successor_scenario_id"] = "EXTRA-001"
        catalog["entries"].append(extra)
    else:
        catalog["entries"].append(copy.deepcopy(catalog["entries"][0]))
    with pytest.raises(AssertionError):
        _validate_catalog(catalog)


def test_unknown_dependency_and_cycle_are_rejected() -> None:
    catalog = copy.deepcopy(_catalog())
    entries = _entry_map(catalog)
    entries["LINE-REACT-DELIVERY-QUERY-001"]["dependencies"] = [
        {"scenario_id": "UNKNOWN-001", "type": "hard-dependency"}
    ]
    with pytest.raises(AssertionError, match="dangling dependency"):
        _assert_acyclic(entries)

    catalog = copy.deepcopy(_catalog())
    entries = _entry_map(catalog)
    entries["KN-REACT-CATALOG-QUERY-001"]["dependencies"] = [
        {"scenario_id": "KN-REACT-LIFECYCLE-001", "type": "hard-dependency"}
    ]
    with pytest.raises(pytest.fail.Exception, match="dependency cycle"):
        _assert_acyclic(entries)


def test_unknown_disposition_and_dangling_artifact_are_rejected() -> None:
    catalog = copy.deepcopy(_catalog())
    catalog["entries"][0]["disposition"] = "AUTO_APPROVED"
    with pytest.raises(AssertionError):
        for entry in catalog["entries"]:
            assert entry["disposition"] in ALLOWED_DISPOSITIONS

    catalog = copy.deepcopy(_catalog())
    catalog["coverage_records"][0]["fixture_paths"] = ["validation/fixtures/does-not-exist.json"]
    with pytest.raises(AssertionError):
        for relative_path in catalog["coverage_records"][0]["fixture_paths"]:
            assert _resolve(relative_path).is_file()


def test_phase4_json_contains_no_obvious_secret_or_direct_identifier() -> None:
    paths = {CATALOG_PATH, RECEIPT_PATH}
    paths.update((ROOT / "validation/fixtures/phase4").glob("*.json"))
    paths.update((ROOT / "validation/expected/phase4").glob("*.json"))
    for entry in _catalog()["entries"]:
        paths.add(_resolve(entry["scenario_path"]))
    patterns = [
        re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
        re.compile(r"sk-[A-Za-z0-9]{12,}"),
        re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
        re.compile(r"(?<!\d)09\d{8}(?!\d)"),
        re.compile(r"(?<!\d)\d{12,16}(?!\d)"),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert pattern.search(text) is None, f"sensitive-looking data in {path}: {pattern.pattern}"


def test_validator_has_no_skipped_or_focused_tests() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "pytest.mark." + "skip" not in source
    assert "." + "only(" not in source
    assert "." + "todo(" not in source
