"""
File: verification_gate_report.py
Description: 產出分離 baseline 與 Phase 3 lineage 的唯讀契約門報告。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_verification_baseline import load_baseline, verify_baseline
from scripts.verify_verification_receipts import (
    load_receipts,
    receipt_coverage_report,
    verify_receipts,
)
from scripts.verify_verification_scenarios import (
    load_scenarios,
    scenario_coverage_report,
    verify_scenarios,
)
from scripts.verify_verification_fixtures import (
    PHASE3_NAMESPACE,
    discover_fixture_documents,
    fixture_coverage_report,
    load_fixtures,
    verify_fixture_documents,
)
from scripts.verify_field_authority_legacy_names import (
    audit_report as field_authority_audit_report,
    load_manifest as load_field_authority_manifest,
    verify_manifest as verify_field_authority_manifest,
)


PHASE3_CATALOG_PATH = PROJECT_ROOT / "validation" / "catalog" / "phase3_scenario_lineage.json"


def _phase3_catalog() -> tuple[dict[str, object] | None, list[str]]:
    if not PHASE3_CATALOG_PATH.is_file():
        return None, ["Phase 3 lineage catalog is missing"]
    try:
        catalog = json.loads(PHASE3_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"Phase 3 lineage catalog is invalid: {type(exc).__name__}"]
    if not isinstance(catalog, dict):
        return None, ["Phase 3 lineage catalog has an unsupported shape"]
    errors: list[str] = []
    if catalog.get("contract") != "labor-union-phase3-lineage-catalog/v1":
        errors.append("Phase 3 lineage catalog has an unsupported contract")
    entries = catalog.get("entries")
    expected_ids = catalog.get("expected_scenario_ids")
    if not isinstance(entries, list) or not isinstance(expected_ids, list):
        return catalog, errors + ["Phase 3 lineage catalog must define entries and expected_scenario_ids"]
    entry_ids = [entry.get("scenario_id") for entry in entries if isinstance(entry, dict)]
    string_entry_ids = [item for item in entry_ids if isinstance(item, str)]
    string_expected_ids = [item for item in expected_ids if isinstance(item, str)]
    if len(string_entry_ids) != len(entry_ids):
        errors.append("Phase 3 lineage catalog has a non-string scenario identity")
    if len(string_expected_ids) != len(expected_ids):
        errors.append("Phase 3 lineage catalog has a non-string expected scenario id")
    if len(set(string_entry_ids)) != len(string_entry_ids):
        errors.append("Phase 3 lineage catalog has duplicate scenario identity")
    if set(string_entry_ids) != set(string_expected_ids):
        errors.append("Phase 3 lineage catalog expected scenario set does not match entries")
    return catalog, errors


def _phase3_asset_errors(catalog: dict[str, object] | None) -> list[str]:
    if catalog is None:
        return []
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return []
    errors: list[str] = []
    seen_paths: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("Phase 3 lineage catalog has an unsupported entry shape")
            continue
        scenario_id = entry.get("scenario_id")
        for field, root in (
            ("scenario_path", PROJECT_ROOT / "validation" / "scenarios"),
            ("fixture_path", PROJECT_ROOT / "validation" / "fixtures" / PHASE3_NAMESPACE),
            ("expected_path", PROJECT_ROOT / "validation" / "expected" / PHASE3_NAMESPACE),
        ):
            value = entry.get(field)
            path = (PROJECT_ROOT / value).resolve() if isinstance(value, str) else None
            if path is None or not path.is_file():
                errors.append(f"Phase 3 {field} is missing for {scenario_id}")
                continue
            try:
                path.relative_to(root.resolve())
            except ValueError:
                errors.append(f"Phase 3 {field} is outside its namespace for {scenario_id}")
            if field != "scenario_path":
                if path in seen_paths:
                    errors.append(f"Phase 3 duplicate asset path: {value}")
                seen_paths.add(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f"Phase 3 {field} is invalid JSON for {scenario_id}: {type(exc).__name__}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"Phase 3 {field} has an unsupported shape for {scenario_id}")
            elif payload.get("scenario_id") != scenario_id:
                errors.append(f"Phase 3 {field} has a mismatched scenario for {scenario_id}")
    return errors


def build_gate_report() -> dict[str, object]:
    baseline = load_baseline()
    scenarios = load_scenarios()
    phase3_catalog, phase3_catalog_errors = _phase3_catalog()
    raw_phase3_ids = phase3_catalog.get("expected_scenario_ids", []) if phase3_catalog else []
    phase3_ids = {
        item for item in raw_phase3_ids if isinstance(item, str)
    } if isinstance(raw_phase3_ids, list) else set()
    baseline_scenarios = [
        scenario for scenario in scenarios if scenario.get("scenario_id") not in phase3_ids
    ]
    phase3_scenarios = [
        scenario for scenario in scenarios if scenario.get("scenario_id") in phase3_ids
    ]
    receipts = load_receipts()
    fixtures = load_fixtures()
    fixture_documents, fixture_discovery_errors = discover_fixture_documents()
    baseline_documents = [
        document for document in fixture_documents if document.namespace == "baseline"
    ]
    phase3_documents = [
        document for document in fixture_documents if document.namespace == PHASE3_NAMESPACE
    ]
    baseline_fixture_family = verify_fixture_documents(baseline_documents, baseline_scenarios)
    phase3_fixture_family = verify_fixture_documents(phase3_documents, phase3_scenarios)
    field_authority_manifest = load_field_authority_manifest()
    baseline_errors = verify_baseline(baseline)
    scenario_errors = verify_scenarios(scenarios, baseline)
    receipt_errors = verify_receipts(receipts, baseline_scenarios)
    fixture_errors = baseline_fixture_family["baseline"]
    phase3_fixture_errors = phase3_fixture_family["phase3"]
    phase3_lineage_errors = (
        phase3_catalog_errors
        + _phase3_asset_errors(phase3_catalog)
        + fixture_discovery_errors
        + phase3_fixture_errors
    )
    field_authority_errors = verify_field_authority_manifest(field_authority_manifest)
    scenario_coverage = scenario_coverage_report(scenarios, baseline)
    receipt_coverage = receipt_coverage_report(receipts, baseline_scenarios)
    track_contracts = _track_contracts(baseline, scenarios)
    report = {
        "release_id": baseline["release_id"],
        "contract_valid": not (
            baseline_errors or scenario_errors or fixture_errors or phase3_lineage_errors or receipt_errors
            or field_authority_errors
        ),
        "errors": {
            "baseline": baseline_errors,
            "scenarios": scenario_errors,
            "fixtures": fixture_errors,
            "phase3_lineage": phase3_lineage_errors,
            "receipts": receipt_errors,
            "field_authority": field_authority_errors,
        },
        "tracks": track_contracts,
        "suite_execution": _suite_execution_report(baseline, baseline_scenarios, receipts),
        "business_matrix": {
            "required": scenario_coverage["business_requirement_count"],
            "missing": scenario_coverage["business_requirements_missing"],
        },
        "fixtures": {
            "valid": not fixture_errors,
            **fixture_coverage_report(fixtures, baseline_scenarios),
        },
        "phase3_lineage": {
            "valid": not phase3_lineage_errors,
            "scenario_count": len(phase3_scenarios),
            "fixture_count": len([
                document for document in fixture_documents
                if document.namespace == PHASE3_NAMESPACE
            ]),
            "expected_manifest_namespace": "validation/expected/phase3",
            "errors": phase3_lineage_errors,
            "runtime_receipts": "metadata-only; no PASS inferred",
        },
        "field_authority": field_authority_audit_report(field_authority_manifest),
        "evidence_boundaries": _evidence_boundary_report(baseline_scenarios, receipts),
        "blocked_scenarios": _blocked_scenarios(baseline_scenarios),
        "receipts": receipt_coverage,
        "database_execution": _database_execution_report(receipts, baseline_scenarios),
        "overall_complete": False,
    }
    report["baseline_deliverables"] = _baseline_deliverables(report, baseline)
    report["baseline_established"] = all(
        item["satisfied"] for item in report["baseline_deliverables"]
    )
    return report


def _track_contracts(
    baseline: dict[str, object], scenarios: list[dict[str, object]]
) -> list[dict[str, object]]:
    present_suites = {scenario["suite_id"] for scenario in scenarios}
    return [
        {
            "track": track["id"],
            "contract_suites": len(track["suites"]),
            "suites_missing_contract": [
                suite["id"] for suite in track["suites"] if suite["id"] not in present_suites
            ],
        }
        for track in baseline["tracks"]
    ]


def _baseline_deliverables(
    report: dict[str, object], baseline: dict[str, object],
) -> list[dict[str, object]]:
    tracks = report["tracks"]
    boundaries = report["evidence_boundaries"]
    fixture_report = report["fixtures"]
    database_report = report["database_execution"]
    track_kinds = {
        track["id"]: {
            kind for suite in track["suites"] for kind in suite["test_kinds"]
        }
        for track in baseline["tracks"]
    }
    observed_kinds = {
        row["track"]: set(row["test_kinds"])
        for row in boundaries
    }
    return [
        _deliverable("versioned_track_contracts", all(not row["suites_missing_contract"] for row in tracks)),
        _deliverable("business_matrix_mapped", not report["business_matrix"]["missing"]),
        _deliverable("a_fixture_and_expected_contracts", fixture_report["all_a_scenarios_have_fixture"]),
        _deliverable("track_test_kind_boundaries", all(track_kinds[key] <= observed_kinds.get(key, set()) for key in track_kinds)),
        _deliverable("validators_and_receipts", report["contract_valid"]),
        _deliverable("confirmed_lu_test_database_execution", database_report["execution_evidence_recorded"]),
        _deliverable("track_a_and_b_receipts", _has_receipt_for_each_track(report)),
    ]


def _deliverable(name: str, satisfied: object) -> dict[str, object]:
    return {"name": name, "satisfied": bool(satisfied)}


def _has_receipt_for_each_track(report: dict[str, object]) -> bool:
    suite_rows = report["suite_execution"]
    return all(
        any(row["passed_supplemental_scenario_ids"] for row in suite_rows if row["track"] == track)
        for track in ("A", "B")
    )


def _suite_execution_report(
    baseline: dict[str, object], scenarios: list[dict[str, object]],
    receipts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep supplemental evidence separate from each suite's full matrix contract."""
    passed_ids = {
        receipt["scenario_id"] for receipt in receipts if receipt.get("result") == "passed"
    }
    rows: list[dict[str, object]] = []
    for track in baseline["tracks"]:
        for suite in track["suites"]:
            suite_scenarios = [
                scenario for scenario in scenarios if scenario.get("suite_id") == suite["id"]
            ]
            matrix_ids = sorted(
                scenario["scenario_id"]
                for scenario in suite_scenarios
                if scenario.get("coverage_scope", "matrix") == "matrix"
            )
            supplemental_ids = sorted(
                scenario["scenario_id"]
                for scenario in suite_scenarios
                if scenario.get("coverage_scope") == "supplemental"
            )
            passed_kinds = {
                test_kind
                for scenario in suite_scenarios
                if scenario.get("scenario_id") in passed_ids
                for test_kind in scenario.get("test_kinds", [])
            }
            missing_matrix = sorted(set(matrix_ids) - passed_ids)
            missing_kinds = sorted(set(suite["test_kinds"]) - passed_kinds)
            rows.append({
                "track": track["id"],
                "suite_id": suite["id"],
                "matrix_scenario_ids": matrix_ids,
                "unverified_matrix_scenario_ids": missing_matrix,
                "passed_supplemental_scenario_ids": sorted(set(supplemental_ids) & passed_ids),
                "test_kinds_without_passing_receipt": missing_kinds,
                "full_suite_verified": not missing_matrix and not missing_kinds,
            })
    return rows


def _database_execution_report(
    receipts: list[dict[str, object]], scenarios: list[dict[str, object]],
) -> dict[str, object]:
    passed_scenarios = sorted(
        receipt["scenario_id"]
        for receipt in receipts
        if receipt.get("result") == "passed"
        and isinstance(receipt.get("environment"), dict)
        and receipt["environment"].get("database") not in {None, "none"}
    )
    scenarios_by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    passed_by_execution_mode: dict[str, list[str]] = {}
    for scenario_id in passed_scenarios:
        mode = scenarios_by_id[scenario_id].get("database_execution_mode", "not_declared")
        passed_by_execution_mode.setdefault(str(mode), []).append(scenario_id)
    return {
        "authorization_policy": "Execution requires an explicitly confirmed lu_test_* target database.",
        "passed_disposable_database_scenarios": passed_scenarios,
        "passed_by_execution_mode": passed_by_execution_mode,
        "execution_evidence_recorded": bool(passed_scenarios),
    }


def _evidence_boundary_report(
    scenarios: list[dict[str, object]], receipts: list[dict[str, object]]
) -> list[dict[str, object]]:
    passed_scenario_ids = {
        receipt["scenario_id"] for receipt in receipts if receipt.get("result") == "passed"
    }
    rows: list[dict[str, object]] = []
    for track in ("A", "B"):
        counts: dict[str, dict[str, int]] = {}
        for scenario in scenarios:
            if scenario.get("track") != track:
                continue
            for test_kind in scenario.get("test_kinds", []):
                row = counts.setdefault(
                    test_kind,
                    {"declared_scenarios": 0, "bound_scenarios": 0, "passing_receipts": 0},
                )
                row["declared_scenarios"] += 1
                if scenario.get("status") == "bound":
                    row["bound_scenarios"] += 1
                if scenario.get("scenario_id") in passed_scenario_ids:
                    row["passing_receipts"] += 1
        rows.append({"track": track, "test_kinds": counts})
    return rows


def _blocked_scenarios(scenarios: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "scenario_id": str(scenario["scenario_id"]),
            "track": str(scenario["track"]),
            "suite_id": str(scenario["suite_id"]),
            "blocker": str(scenario["blocker"]),
        }
        for scenario in scenarios
        if scenario.get("status") == "blocked"
    ]


def write_gate_report(output_path: Path, report: dict[str, object]) -> None:
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = build_gate_report()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output is not None:
        write_gate_report(arguments.output, report)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
