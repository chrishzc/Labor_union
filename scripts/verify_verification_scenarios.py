"""
File: verify_verification_scenarios.py
Description: 載入並驗證版本化業務與基礎設施情境契約。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_verification_baseline import DEFAULT_BASELINE_PATH, load_baseline


DEFAULT_SCENARIO_DIRECTORY = PROJECT_ROOT / "validation" / "scenarios"
SCENARIO_CONTRACT = "labor-union-verification-scenario/v1"
SCENARIO_STATUS = {"specified", "bound", "blocked"}
NON_SCENARIO_ARTIFACTS = frozenset(
    {
        "react_admin_entrypoints.json",
        "react_admin_retirement_requirements.json",
    }
)
DATABASE_EXECUTION_MODES = {
    "persistent_append_only",
    "read_only_existing_database",
    "fresh_schema_bootstrap",
}
NONEXISTENT_HISTORICAL_SOURCE = (
    "document/架構重整/01_規格基線/28_驗證情境與測試資料正式規格.md"
)


def load_scenarios(directory: Path = DEFAULT_SCENARIO_DIRECTORY) -> list[dict[str, object]]:
    scenarios: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"verification scenario artifact must be a JSON object: {path.name}"
            )
        if payload.get("contract") == SCENARIO_CONTRACT:
            scenarios.append(payload)
            continue
        if path.name in NON_SCENARIO_ARTIFACTS:
            continue
        raise ValueError(
            f"unsupported verification scenario artifact: {path.name}"
        )
    return scenarios


def verify_scenarios(
    scenarios: list[dict[str, object]], baseline: dict[str, object] | None = None,
    business_requirement_ids: set[str] | None = None,
) -> list[str]:
    baseline = baseline or load_baseline(DEFAULT_BASELINE_PATH)
    business_requirement_ids = business_requirement_ids or canonical_business_requirement_ids()
    suite_tracks = _suite_tracks(baseline)
    suite_test_kinds = _suite_test_kinds(baseline)
    scenario_ids: set[str] = set()
    errors: list[str] = []
    for scenario in scenarios:
        errors.extend(
            _scenario_errors(
                scenario,
                suite_tracks,
                scenario_ids,
                business_requirement_ids,
                suite_test_kinds,
            )
        )
    errors.extend(_completeness_errors(scenarios, suite_tracks, business_requirement_ids))
    return errors


def scenario_coverage_report(
    scenarios: list[dict[str, object]], baseline: dict[str, object] | None = None,
    business_requirement_ids: set[str] | None = None,
) -> dict[str, object]:
    baseline = baseline or load_baseline(DEFAULT_BASELINE_PATH)
    business_requirement_ids = business_requirement_ids or canonical_business_requirement_ids()
    suite_tracks = _suite_tracks(baseline)
    present = {scenario["suite_id"] for scenario in scenarios if "suite_id" in scenario}
    covered_business_ids = {
        coverage_id
        for scenario in scenarios
        if scenario.get("track") == "A" and scenario.get("coverage_scope", "matrix") == "matrix"
        for coverage_id in scenario.get("coverage_ids", [])
    }
    return {
        "scenario_count": len(scenarios),
        "suites_without_scenario": sorted(set(suite_tracks) - present),
        "scenario_ids": [scenario["scenario_id"] for scenario in scenarios],
        "business_requirement_count": len(business_requirement_ids),
        "business_requirements_missing": sorted(
            business_requirement_ids - covered_business_ids
        ),
    }


def _suite_tracks(baseline: dict[str, object]) -> dict[str, str]:
    return {
        suite["id"]: track["id"]
        for track in baseline["tracks"]
        for suite in track["suites"]
    }


def _suite_test_kinds(baseline: dict[str, object]) -> dict[str, set[str]]:
    return {
        suite["id"]: set(suite["test_kinds"])
        for track in baseline["tracks"]
        for suite in track["suites"]
    }


def canonical_business_requirement_ids(
    directory: Path = DEFAULT_SCENARIO_DIRECTORY,
) -> set[str]:
    """Read Track A matrix coverage identities from checked-in scenario contracts."""
    return {
        coverage_id
        for scenario in load_scenarios(directory)
        if scenario.get("track") == "A"
        and scenario.get("coverage_scope", "matrix") == "matrix"
        for coverage_id in scenario.get("coverage_ids", [])
        if isinstance(coverage_id, str)
    }


def _scenario_errors(
    scenario: dict[str, object], suite_tracks: dict[str, str], scenario_ids: set[str],
    business_requirement_ids: set[str], suite_test_kinds: dict[str, set[str]],
) -> list[str]:
    scenario_id = scenario.get("scenario_id")
    errors: list[str] = []
    if scenario.get("contract") != SCENARIO_CONTRACT:
        errors.append(f"scenario {scenario_id} has an unsupported contract")
    if not isinstance(scenario_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+", scenario_id):
        errors.append("scenario has an invalid scenario_id")
    elif scenario_id in scenario_ids:
        errors.append(f"duplicate scenario id: {scenario_id}")
    else:
        scenario_ids.add(scenario_id)
    suite_id = scenario.get("suite_id")
    track = scenario.get("track")
    if suite_tracks.get(suite_id) != track:
        errors.append(f"scenario {scenario_id} has an unknown suite or wrong track")
    if scenario.get("status") not in SCENARIO_STATUS:
        errors.append(f"scenario {scenario_id} has an invalid status")
    if scenario.get("status") == "blocked" and not _has_blocker(scenario.get("blocker")):
        errors.append(f"scenario {scenario_id} must define a blocker")
    if scenario.get("status") == "bound":
        errors.extend(_execution_binding_errors(scenario_id, scenario.get("execution")))
        errors.extend(_database_execution_mode_errors(scenario_id, scenario))
    if not isinstance(scenario.get("requires_database"), bool):
        errors.append(f"scenario {scenario_id} must declare requires_database")
    for field in ("test_kinds", "source_refs", "root_facts", "forbidden_direct_seed", "commands", "expected", "receipt_requirements"):
        if not isinstance(scenario.get(field), list) or not scenario[field]:
            errors.append(f"scenario {scenario_id} must define {field}")
    test_kinds = scenario.get("test_kinds")
    if isinstance(test_kinds, list):
        if any(not isinstance(test_kind, str) for test_kind in test_kinds):
            errors.append(f"scenario {scenario_id} has a non-string test_kind")
        if len(set(test_kinds)) != len(test_kinds):
            errors.append(f"scenario {scenario_id} has duplicate test_kinds")
        if any(test_kind not in suite_test_kinds.get(suite_id, set()) for test_kind in test_kinds):
            errors.append(f"scenario {scenario_id} has a test_kind outside its suite contract")
        expected = scenario.get("expected")
        if isinstance(expected, list) and len(expected) < len(test_kinds):
            errors.append(f"scenario {scenario_id} has incomplete acceptance criteria")
    errors.extend(_source_reference_errors(scenario_id, scenario.get("source_refs")))
    coverage_ids = scenario.get("coverage_ids")
    if not isinstance(coverage_ids, list) or not coverage_ids:
        errors.append(f"scenario {scenario_id} must define coverage_ids")
    elif scenario.get("coverage_scope", "matrix") not in {"matrix", "supplemental"}:
        errors.append(f"scenario {scenario_id} has an invalid coverage scope")
    elif track == "A" and scenario.get("coverage_scope", "matrix") == "matrix" and any(
        coverage_id not in business_requirement_ids for coverage_id in coverage_ids
    ):
        errors.append(f"scenario {scenario_id} has unknown business coverage ids")
    elif track == "B" and any(
        not isinstance(coverage_id, str) or not coverage_id.startswith(f"{suite_id}-")
        for coverage_id in coverage_ids
    ):
        errors.append(f"scenario {scenario_id} has invalid infrastructure coverage ids")
    return errors


def _completeness_errors(
    scenarios: list[dict[str, object]], suite_tracks: dict[str, str],
    business_requirement_ids: set[str],
) -> list[str]:
    present_suites = {scenario.get("suite_id") for scenario in scenarios}
    missing_suites = sorted(set(suite_tracks) - present_suites)
    errors: list[str] = []
    if missing_suites:
        errors.append(f"missing scenario contracts for suites: {', '.join(missing_suites)}")
    covered_matrix_ids = {
        coverage_id
        for scenario in scenarios
        if scenario.get("track") == "A" and scenario.get("coverage_scope", "matrix") == "matrix"
        for coverage_id in scenario.get("coverage_ids", [])
    }
    missing_requirements = sorted(business_requirement_ids - covered_matrix_ids)
    if missing_requirements:
        errors.append(
            f"missing business requirement mappings: {', '.join(missing_requirements)}"
        )
    return errors


def _source_reference_errors(scenario_id: object, source_refs: object) -> list[str]:
    if not isinstance(source_refs, list):
        return []
    missing = [
        source_ref
        for source_ref in source_refs
        if not _is_nonexistent_historical_source(source_ref)
        and not _source_reference_exists(source_ref)
    ]
    if missing:
        return [f"scenario {scenario_id} has a missing source reference"]
    return []


def _is_nonexistent_historical_source(source_ref: object) -> bool:
    return (
        isinstance(source_ref, str)
        and source_ref.partition("#")[0] == NONEXISTENT_HISTORICAL_SOURCE
    )


def _source_reference_exists(source_ref: object) -> bool:
    if not isinstance(source_ref, str):
        return False
    path_text, separator, anchor = source_ref.partition("#")
    path = PROJECT_ROOT / path_text
    if not path.is_file():
        return False
    return bool(separator) and bool(anchor) and anchor in path.read_text(encoding="utf-8")


def _execution_binding_errors(scenario_id: object, execution: object) -> list[str]:
    if not isinstance(execution, dict):
        return [f"scenario {scenario_id} must define execution binding"]
    runner = execution.get("runner")
    test_paths = execution.get("test_paths")
    if not isinstance(runner, list) or not runner:
        return [f"scenario {scenario_id} must define execution runner"]
    if not isinstance(test_paths, list) or not test_paths:
        return [f"scenario {scenario_id} must define execution test_paths"]
    if any(not isinstance(path, str) or not (PROJECT_ROOT / path).is_file() for path in test_paths):
        return [f"scenario {scenario_id} has a missing execution test path"]
    return []


def _database_execution_mode_errors(
    scenario_id: object, scenario: dict[str, object],
) -> list[str]:
    if scenario.get("requires_database") is not True:
        return []
    if scenario.get("database_execution_mode") not in DATABASE_EXECUTION_MODES:
        return [f"scenario {scenario_id} must define a safe database execution mode"]
    return []


def _has_blocker(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def main() -> int:
    scenarios = load_scenarios()
    errors = verify_scenarios(scenarios)
    print(json.dumps({"valid": not errors, "errors": errors, "coverage": scenario_coverage_report(scenarios)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
