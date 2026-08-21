"""
File: test_phase3_scenario_lineage.py
Description: 驗證 Phase 3 scenario lineage、fixture、oracle、清單與 receipt catalog 的反偷懶契約。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.verification_gate_report import build_gate_report
from scripts.verify_verification_fixtures import (
    FixtureDocument,
    discover_fixture_documents,
    load_fixtures,
    verify_fixture_documents,
    verify_fixtures,
)
from scripts.verify_verification_scenarios import load_scenarios, verify_scenarios


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "validation/catalog/phase3_scenario_lineage.json"
RECEIPT_PATH = ROOT / "validation/receipts/phase3/manifest.json"
SCENARIO_DIR = ROOT / "validation/scenarios"
FIXTURE_DIR = ROOT / "validation/fixtures/phase3"
EXPECTED_DIR = ROOT / "validation/expected/phase3"
CHECKLIST_MANIFEST = ROOT / "validation/ui_business_workflows/checklist_manifest.yaml"

EXPECTED_IDS = {
    "GERR-REACT-ADMIN-TYPED-BOUNDARY",
    "SCH-REACT-ADMIN-STAFF-SAFE-ACTIONS",
    "SCH-REACT-ADMIN-CURRENT-QUERY",
    "SCH-REACT-ADMIN-LEAVE-SUBSTITUTION",
    "SCH-REACT-ADMIN-HOLIDAY-POLICY",
    "AC-REACT-ADMIN-AUDIT-QUERY",
    "ANOM-REACT-ADMIN-WARNING-TRANSITION",
    "GDATA-REACT-ADMIN-DATA-BROWSER-QUERY",
}
ALLOWED_DEPENDENCY_TYPES = {
    "hard-dependency",
    "soft-dependency",
    "independent-lane",
    "global-dependency",
}
FORBIDDEN_RESULT_WORDS = ("pass", "passed", "completed", "success")
WORK_PACKAGE_IDENTITY = "PROV-20260817-react-admin-phase3-scenario-lineage-governance"
HOLIDAY_SCENARIO_ID = "SCH-REACT-ADMIN-HOLIDAY-POLICY"
HOLIDAY_SUCCESSOR_IDENTITY = (
    "PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor"
)
REQUIRED_CATALOG_LINEAGE_FIELDS = {
    "work_package_identity",
    "source_scenario_ids",
    "source_refs",
    "source_to_successor_mapping",
    "business_clock",
    "commands",
    "oracle_applicability",
    "browser_execution_mode",
    "missing_artifacts",
    "data_classification",
    "generation_method",
    "allowed_use",
    "redaction_policy",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_repo_path(relative_path: str) -> Path:
    path = ROOT / relative_path
    assert path.is_file(), f"missing referenced artifact: {relative_path}"
    return path


def _catalog() -> dict:
    return _load_json(CATALOG_PATH)


def _entries_by_id() -> dict[str, dict]:
    entries = _catalog()["entries"]
    return {entry["scenario_id"]: entry for entry in entries}


def _assert_acyclic(entries: dict[str, dict]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(scenario_id: str) -> None:
        if scenario_id in visiting:
            raise AssertionError(f"dependency cycle at {scenario_id}")
        if scenario_id in visited:
            return
        visiting.add(scenario_id)
        for dependency in entries[scenario_id]["dependencies"]:
            visit(dependency["scenario_id"])
        visiting.remove(scenario_id)
        visited.add(scenario_id)

    for scenario_id in entries:
        visit(scenario_id)


def test_catalog_expected_set_is_independent_and_complete() -> None:
    catalog = _catalog()
    assert set(catalog["expected_scenario_ids"]) == EXPECTED_IDS
    entries = _entries_by_id()
    assert set(entries) == EXPECTED_IDS
    assert len(catalog["entries"]) == len(EXPECTED_IDS)
    assert len(entries) == len(catalog["entries"])


def test_catalog_paths_and_dependency_dag_are_strict() -> None:
    entries = _entries_by_id()
    assert len({entry["scenario_path"] for entry in entries.values()}) == len(entries)
    assert len({entry["fixture_path"] for entry in entries.values()}) == len(entries)
    assert len({entry["expected_path"] for entry in entries.values()}) == len(entries)
    assert len({entry["receipt_id"] for entry in entries.values()}) == len(entries)
    for entry in entries.values():
        _resolve_repo_path(entry["scenario_path"])
        _resolve_repo_path(entry["fixture_path"])
        _resolve_repo_path(entry["expected_path"])
        for dependency in entry["dependencies"]:
            assert dependency["scenario_id"] in entries
            assert dependency["type"] in ALLOWED_DEPENDENCY_TYPES
    _assert_acyclic(entries)


def test_catalog_entries_preserve_scenario_and_fixture_lineage() -> None:
    for scenario_id, entry in _entries_by_id().items():
        assert REQUIRED_CATALOG_LINEAGE_FIELDS <= entry.keys()
        expected_identity = (
            HOLIDAY_SUCCESSOR_IDENTITY
            if scenario_id == HOLIDAY_SCENARIO_ID
            else WORK_PACKAGE_IDENTITY
        )
        assert entry["work_package_identity"] == expected_identity
        assert entry["source_refs"]
        assert entry["source_to_successor_mapping"]
        assert entry["business_clock"]
        assert entry["commands"]
        assert entry["oracle_applicability"]
        expected_browser_mode = (
            "controlled-execution"
            if scenario_id == HOLIDAY_SCENARIO_ID
            else "no-browser-execution"
        )
        assert entry["browser_execution_mode"] == expected_browser_mode
        assert entry["missing_artifacts"]
        assert entry["data_classification"] in {
            "synthetic",
            "deidentified",
            "invalid-by-design",
        }
        assert entry["generation_method"]
        assert entry["allowed_use"] == "validation-only"
        assert entry["redaction_policy"]

        scenario = _load_json(_resolve_repo_path(entry["scenario_path"]))
        fixture = _load_json(_resolve_repo_path(entry["fixture_path"]))
        for field in (
            "source_scenario_ids",
            "source_refs",
            "source_to_successor_mapping",
            "business_clock",
            "commands",
            "oracle_applicability",
            "browser_execution_mode",
        ):
            assert entry[field] == scenario[field], f"{scenario_id}: catalog drift at {field}"
        assert entry["data_classification"] == fixture["data_classification"]
        assert entry["generation_method"] == fixture["generation_method"]
        assert entry["allowed_use"] == fixture["allowed_use"]
        assert entry["redaction_policy"] == fixture["redaction_policy"]


def test_scenarios_match_catalog_and_have_source_lineage() -> None:
    for scenario_id, entry in _entries_by_id().items():
        scenario = _load_json(_resolve_repo_path(entry["scenario_path"]))
        assert scenario["scenario_id"] == scenario_id
        assert scenario["revision"] == entry["revision"]
        assert scenario["suite_id"] == entry["suite_id"]
        assert scenario["track"] == entry["track"]
        assert scenario["source_to_successor_mapping"]
        for source_ref in scenario["source_refs"]:
            source_path = ROOT / source_ref.split("#", 1)[0]
            assert source_path.is_file(), f"missing source reference: {source_ref}"
        if scenario_id != "GDATA-REACT-ADMIN-DATA-BROWSER-QUERY":
            assert scenario["source_scenario_ids"]
        else:
            assert scenario["status"] == "blocked"
            assert scenario["activation_blocker"].startswith("BLOCKED_DECISION")


def test_fixture_metadata_and_root_boundary_are_fail_closed() -> None:
    required = {"data_classification", "generation_method", "allowed_use", "redaction_policy"}
    for fixture_path in FIXTURE_DIR.glob("*.json"):
        fixture = _load_json(fixture_path)
        assert required <= fixture.keys()
        assert fixture["data_classification"] in {"synthetic", "deidentified", "invalid-by-design"}
        assert fixture["allowed_use"] == "validation-only"
        root_serialized = json.dumps(fixture["root_inputs"], ensure_ascii=False).lower()
        assert not any(term in root_serialized for term in ("@", "sk-", "bearer ", "phone", "bank_account"))
        assert "forbidden_direct_seed" in fixture


def test_expected_files_contain_oracles_but_no_observed_payload() -> None:
    forbidden_keys = {"actual", "observed", "runtime_receipt", "generated_receipt"}
    expected_paths = sorted(EXPECTED_DIR.glob("*.json")) + sorted(EXPECTED_DIR.glob("*.yaml"))
    for expected_path in expected_paths:
        expected = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
        assert {"db_oracle", "api_oracle", "ui_oracle", "replay_oracle", "recovery_oracle"} <= expected.keys()
        assert not forbidden_keys.intersection(expected)


def test_ui_manifest_and_receipt_registry_are_not_runtime_claims() -> None:
    ui_manifest = yaml.safe_load(CHECKLIST_MANIFEST.read_text(encoding="utf-8"))
    assert ui_manifest["execution_policy"]["mode"] == "no-browser-execution"
    assert {part["status"] for part in ui_manifest["parts"]} == {"NOT_RUN"}
    receipt_manifest = _load_json(RECEIPT_PATH)
    assert set(receipt_manifest["allowed_initial_states"]) == {
        "missing",
        "not_run",
        "blocked",
        "partial",
    }
    assert all(receipt["status"] in receipt_manifest["allowed_initial_states"] for receipt in receipt_manifest["receipts"])
    entries = _entries_by_id()
    assert all(
        receipt["revision"] == entries[receipt["scenario_id"]]["revision"]
        for receipt in receipt_manifest["receipts"]
    )
    assert {
        (receipt["scenario_id"], receipt["receipt_id"])
        for receipt in receipt_manifest["receipts"]
    } == {
        (entry["scenario_id"], entry["receipt_id"])
        for entry in _entries_by_id().values()
    }
    assert not any(receipt["status"] == "missing" and "result" in receipt for receipt in receipt_manifest["receipts"])


def test_result_summaries_are_initial_and_do_not_fake_completion() -> None:
    for summary_path in ROOT.glob("validation/ui_business_workflows/part_*/result_summary.md"):
        text = summary_path.read_text(encoding="utf-8").lower()
        if summary_path.parent.name == "part_09_scheduling":
            assert "result: partial" in text
            assert "browser stale variant: pass" in text
            assert "browser same-key replay variant: pass" in text
            assert "browser rollback variant: pass" in text
            assert "browser conflicting-draft pre-transport guard: pass" in text
            assert "browser server-conflict 409 dom variant: not_run" in text
            assert "真totp：not_run" in text
        else:
            assert "result: not_run" in text
            assert not any(word in text for word in FORBIDDEN_RESULT_WORDS)
        assert "assertion count" not in text


def test_holiday_mutation_successor_is_revision_two_and_partial_not_fake_pass() -> None:
    entry = _entries_by_id()[HOLIDAY_SCENARIO_ID]
    scenario = _load_json(_resolve_repo_path(entry["scenario_path"]))
    fixture = _load_json(_resolve_repo_path(entry["fixture_path"]))
    expected = yaml.safe_load(_resolve_repo_path(entry["expected_path"]).read_text(encoding="utf-8"))
    receipt = next(
        item
        for item in _load_json(RECEIPT_PATH)["receipts"]
        if item["scenario_id"] == HOLIDAY_SCENARIO_ID
    )

    assert entry["revision"] == scenario["revision"] == fixture["revision"] == expected["revision"] == 2
    assert entry["receipt_id"] == scenario["required_receipt_id"] == receipt["receipt_id"]
    assert scenario["browser_execution_mode"] == "controlled-execution"
    assert scenario["oracle_applicability"]["replay"]["status"] == "required"
    assert {
        "synthetic holiday mutation command",
        "expected calendar version",
        "preview fingerprint",
        "operator reason",
        "stable idempotency identity",
    } <= set(scenario["root_inputs"])
    assert "apply receipt" in scenario["forbidden_direct_seed"]
    assert receipt["status"] == "partial"
    assert receipt["remaining"] == [
        "browser server-conflict 409 DOM",
        "true-TOTP browser",
    ]


def test_data_browser_cannot_be_marked_ui_ready() -> None:
    entry = _entries_by_id()["GDATA-REACT-ADMIN-DATA-BROWSER-QUERY"]
    scenario = _load_json(ROOT / entry["scenario_path"])
    expected = _load_json(ROOT / entry["expected_path"])
    assert entry["part"] == "BLOCKED_DECISION"
    assert scenario["status"] == "blocked"
    assert expected["ui_oracle"]["applicability"] == "blocked"
    assert entry["checklist_path"] is None
    assert not (ROOT / "validation/ui_business_workflows/part_data_browser").exists()


def test_negative_control_rejects_unknown_dependency_type(tmp_path: Path) -> None:
    candidate = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    candidate["entries"][1]["dependencies"][0]["type"] = "invented-dependency"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    loaded = _load_json(path)
    dependency_type = loaded["entries"][1]["dependencies"][0]["type"]
    assert dependency_type not in ALLOWED_DEPENDENCY_TYPES
    with pytest.raises(AssertionError):
        assert dependency_type in ALLOWED_DEPENDENCY_TYPES


def test_negative_control_rejects_fake_pass_summary(tmp_path: Path) -> None:
    path = tmp_path / "result_summary.md"
    path.write_text("result: PASS\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8").lower()
    with pytest.raises(AssertionError):
        assert "result: not_run" in text and not any(word in text for word in FORBIDDEN_RESULT_WORDS)


def test_canonical_scenario_verifier_accepts_phase3_extension_fields() -> None:
    assert verify_scenarios(load_scenarios()) == []


def test_canonical_fixture_verifier_accepts_nested_phase3_a_fixtures() -> None:
    nested_fixtures = [_load_json(path) for path in sorted(FIXTURE_DIR.glob("*.json"))]
    nested_a_fixtures = [
        fixture
        for fixture in nested_fixtures
        if fixture["scenario_id"] != "GERR-REACT-ADMIN-TYPED-BOUNDARY"
    ]
    assert verify_fixtures(load_fixtures() + nested_a_fixtures, load_scenarios()) == []


def test_track_b_harness_fixture_declares_canonical_shape_without_becoming_a_fixture_a() -> None:
    fixture = _load_json(FIXTURE_DIR / "global_fastapi_typed_error_boundary.json")
    assert fixture["test_kind"] == "process_network_harness"
    assert fixture["root_inputs"]
    assert fixture["seed_fields"]
    assert fixture["derived_fields"]
    assert _resolve_repo_path(fixture["expected_manifest_path"])


def test_canonical_gate_report_separates_phase3_family_without_crashing() -> None:
    report = build_gate_report()
    assert report["errors"]["scenarios"] == []
    assert report["contract_valid"] is False
    assert report["errors"]["fixtures"] == []
    external_phase4_errors = {
        error
        for error in report["errors"]["phase3_lineage"]
        if error.startswith("fixture validation/fixtures/phase4/")
    }
    phase3_owned_errors = [
        error
        for error in report["errors"]["phase3_lineage"]
        if error not in external_phase4_errors
    ]
    assert phase3_owned_errors == []
    assert external_phase4_errors == {
        "fixture validation/fixtures/phase4/react_admin_notification_rule_mutation.json has an unsupported namespace",
        "fixture validation/fixtures/phase4/react_admin_rich_menu_publication.json has an unsupported namespace",
    }
    assert report["fixtures"]["fixture_count"] == len(load_fixtures())
    assert report["phase3_lineage"]["scenario_count"] == 8
    assert report["phase3_lineage"]["fixture_count"] == 8
    assert report["phase3_lineage"]["runtime_receipts"] == "metadata-only; no PASS inferred"


def test_fixture_namespace_mixing_fails_closed() -> None:
    fixture = _load_json(FIXTURE_DIR / "react_admin_staff_safe_actions.json")
    fixture["expected_manifest_path"] = "validation/expected/ORD-LIFECYCLE-001.json"

    errors = verify_fixture_documents(
        [FixtureDocument(path=FIXTURE_DIR / "react_admin_staff_safe_actions.json", payload=fixture, namespace="phase3")],
        load_scenarios(),
    )["baseline"]

    assert errors[0] == (
        "fixture SCH-REACT-ADMIN-STAFF-SAFE-ACTIONS crosses the expected manifest namespace"
    )


def test_recursive_fixture_discovery_reports_malformed_shape(tmp_path: Path) -> None:
    nested = tmp_path / "phase3"
    nested.mkdir()
    (nested / "malformed.json").write_text("[]", encoding="utf-8")

    documents, errors = discover_fixture_documents(tmp_path)

    assert documents == []
    assert errors[0].endswith("has an unsupported shape")
