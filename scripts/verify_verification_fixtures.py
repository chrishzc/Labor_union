"""
File: verify_verification_fixtures.py
Description: 驗證 baseline 與 Phase 3 fixture 的契約分區及 expected manifest。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_verification_scenarios import load_scenarios


DEFAULT_FIXTURE_DIRECTORY = PROJECT_ROOT / "validation" / "fixtures"
FIXTURE_CONTRACT = "labor-union-verification-fixture/v1"
EXPECTED_CONTRACT = "labor-union-verification-expected/v1"
PHASE3_NAMESPACE = "phase3"
PHASE4_NAMESPACE = "phase4"
PHASE3_CATALOG_PATH = PROJECT_ROOT / "validation" / "catalog" / "phase3_scenario_lineage.json"


@dataclass(frozen=True)
class FixtureDocument:
    """One parsed fixture together with its filesystem contract namespace."""

    path: Path
    payload: dict[str, object]
    namespace: str


def discover_fixture_documents(
    directory: Path = DEFAULT_FIXTURE_DIRECTORY,
) -> tuple[list[FixtureDocument], list[str]]:
    """Recursively discover JSON fixtures without mixing contract families."""
    documents: list[FixtureDocument] = []
    errors: list[str] = []
    seen_paths: set[Path] = set()
    if not directory.is_dir():
        return [], [f"fixture directory is missing: {directory}"]
    for path in sorted(directory.rglob("*.json")):
        resolved = path.resolve()
        display_path = _display_path(path)
        if resolved in seen_paths:
            errors.append(f"duplicate fixture path: {display_path}")
            continue
        seen_paths.add(resolved)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(
                f"fixture {display_path} is not valid JSON: {type(exc).__name__}"
            )
            continue
        if not isinstance(payload, dict):
            errors.append(
                f"fixture {display_path} has an unsupported shape"
            )
            continue
        relative_parts = path.relative_to(directory).parts
        namespace = (
            relative_parts[0]
            if relative_parts and relative_parts[0] in {PHASE3_NAMESPACE, PHASE4_NAMESPACE}
            else "baseline"
        )
        if relative_parts and relative_parts[0] not in {PHASE3_NAMESPACE, PHASE4_NAMESPACE} and len(relative_parts) > 1:
            errors.append(f"fixture {display_path} has an unsupported namespace")
            continue
        documents.append(FixtureDocument(path=path, payload=payload, namespace=namespace))
    return documents, errors


def load_fixtures(directory: Path = DEFAULT_FIXTURE_DIRECTORY) -> list[dict[str, object]]:
    documents, errors = discover_fixture_documents(directory)
    if errors:
        raise ValueError("; ".join(errors))
    required_a_ids = {
        str(scenario["scenario_id"])
        for scenario in load_scenarios()
        if scenario.get("track") == "A"
    }
    selected: dict[str, dict[str, object]] = {}
    for document in documents:
        if document.namespace not in {"baseline", PHASE4_NAMESPACE}:
            continue
        scenario_id = document.payload.get("scenario_id")
        if not isinstance(scenario_id, str):
            continue
        if document.namespace == PHASE4_NAMESPACE and scenario_id not in required_a_ids:
            continue
        # A root fixture is the canonical baseline when a Phase 4 package also
        # keeps a more specialised browser/runtime fixture for the same case.
        if scenario_id not in selected or document.namespace == "baseline":
            selected[scenario_id] = document.payload
    return [selected[scenario_id] for scenario_id in sorted(selected)]


def verify_fixtures(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> list[str]:
    """Validate baseline fixtures and any explicitly supplied Phase 3 payloads."""
    scenarios = scenarios or load_scenarios()
    phase3_ids = _phase3_scenario_ids()
    baseline = [
        fixture for fixture in fixtures
        if not _is_phase3_expected_path(fixture.get("expected_manifest_path"))
    ]
    phase3 = [
        fixture for fixture in fixtures
        if _is_phase3_expected_path(fixture.get("expected_manifest_path"))
    ]
    baseline_scenarios = [
        scenario for scenario in scenarios
        if scenario.get("scenario_id") not in phase3_ids
    ]
    phase3_scenarios = [
        scenario for scenario in scenarios
        if scenario.get("scenario_id") in phase3_ids
    ]
    return (
        _verify_fixture_family(baseline, baseline_scenarios, required_track="A")
        + _verify_fixture_family(phase3, phase3_scenarios, required_track=None)
    )


def verify_phase3_fixtures(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> list[str]:
    """Validate Phase 3 fixtures against their own scenario family."""
    return _verify_fixture_family(fixtures, scenarios, required_track=None)


def _verify_fixture_family(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None,
    required_track: str | None,
) -> list[str]:
    scenarios = scenarios or load_scenarios()
    scenario_test_kinds: dict[str, set[str]] = {}
    scenario_tracks: dict[str, object] = {}
    errors: list[str] = []
    for scenario in scenarios:
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str):
            errors.append(f"scenario has an invalid scenario_id for fixture lookup: {scenario_id}")
            continue
        test_kinds = scenario.get("test_kinds")
        if not isinstance(test_kinds, list) or any(not isinstance(kind, str) for kind in test_kinds):
            errors.append(f"scenario {scenario_id} has an invalid test_kinds shape")
            continue
        scenario_test_kinds[scenario_id] = set(test_kinds)
        scenario_tracks[scenario_id] = scenario.get("track")
    fixture_scenario_ids: set[str] = set()
    for fixture in fixtures:
        errors.extend(
            _fixture_errors(
                fixture,
                scenario_test_kinds,
                scenario_tracks,
                fixture_scenario_ids,
                required_track,
            )
        )
    missing = {
        scenario_id for scenario_id, track in scenario_tracks.items()
        if (required_track is None or track == required_track)
    } - fixture_scenario_ids
    if missing and required_track is not None:
        errors.append(f"missing fixtures for A scenarios: {', '.join(sorted(missing))}")
    return errors


def fixture_coverage_report(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> dict[str, object]:
    scenarios = scenarios or load_scenarios()
    phase3_ids = _phase3_scenario_ids()
    required_scenarios = {
        scenario["scenario_id"]
        for scenario in scenarios
        if scenario["track"] == "A" and scenario["scenario_id"] not in phase3_ids
    }
    fixture_scenarios = {
        fixture.get("scenario_id") for fixture in fixtures
        if not _is_phase3_expected_path(fixture.get("expected_manifest_path"))
    }
    return {
        "fixture_count": len(fixtures),
        "required_a_scenario_count": len(required_scenarios),
        "scenarios_without_fixture": sorted(required_scenarios - fixture_scenarios),
        "all_a_scenarios_have_fixture": required_scenarios <= fixture_scenarios,
    }


def _phase3_scenario_ids() -> set[str]:
    try:
        catalog = json.loads(PHASE3_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    ids = catalog.get("expected_scenario_ids") if isinstance(catalog, dict) else None
    return {item for item in ids if isinstance(item, str)} if isinstance(ids, list) else set()


def _is_phase3_expected_path(path_value: object) -> bool:
    return (
        isinstance(path_value, str)
        and path_value.replace("\\", "/").startswith("validation/expected/phase3/")
    )


def _fixture_errors(
    fixture: dict[str, object], scenario_test_kinds: dict[str, set[str]],
    scenario_tracks: dict[str, object], fixture_scenario_ids: set[str],
    required_track: str | None,
) -> list[str]:
    scenario_id = fixture.get("scenario_id")
    errors: list[str] = []
    if fixture.get("contract") != FIXTURE_CONTRACT:
        errors.append(f"fixture {scenario_id} has an unsupported contract")
    track = scenario_tracks.get(scenario_id) if isinstance(scenario_id, str) else None
    if track is None:
        errors.append(f"fixture {scenario_id} must reference a known scenario")
    elif required_track is not None and track != required_track:
        errors.append(f"fixture {scenario_id} must reference an A scenario")
    elif scenario_id in fixture_scenario_ids:
        errors.append(f"duplicate fixture scenario id: {scenario_id}")
    else:
        fixture_scenario_ids.add(scenario_id)
    if fixture.get("test_kind") not in scenario_test_kinds.get(scenario_id, set()):
        errors.append(f"fixture {scenario_id} has an unapproved test_kind")
    if fixture.get("test_kind") not in {
        "domain_root_data", "external_input_fixture", "subsystem_state_machine",
        "typed_query_view", "process_network_harness",
    }:
        errors.append(f"fixture {scenario_id} has an unsupported input boundary")
    for field in ("root_inputs", "seed_fields", "derived_fields"):
        if not isinstance(fixture.get(field), list) or not fixture[field]:
            errors.append(f"fixture {scenario_id} must define {field}")
    seed_fields = fixture.get("seed_fields", [])
    derived_fields = fixture.get("derived_fields", [])
    if isinstance(seed_fields, list) and isinstance(derived_fields, list) and set(seed_fields) & set(derived_fields):
        errors.append(f"fixture {scenario_id} directly seeds derived fields")
    errors.extend(_semantic_derived_seed_errors(scenario_id, seed_fields, derived_fields, fixture))
    errors.extend(_harness_seed_boundary_errors(scenario_id, seed_fields, fixture))
    errors.extend(_expected_manifest_errors(scenario_id, fixture.get("expected_manifest_path")))
    return errors


def _semantic_derived_seed_errors(
    scenario_id: object,
    seed_fields: object,
    derived_fields: object,
    fixture: dict[str, object],
) -> list[str]:
    if not isinstance(seed_fields, list) or not isinstance(derived_fields, list):
        return []
    allowed = fixture.get("permitted_same_named_input_fields", [])
    if not isinstance(allowed, list) or any(not isinstance(field, str) for field in allowed):
        return [f"fixture {scenario_id} has invalid permitted same-named input fields"]
    if any(field not in seed_fields for field in allowed):
        return [f"fixture {scenario_id} permits a non-seed input field"]
    derived_leaves = {_field_leaf(field) for field in derived_fields if isinstance(field, str)}
    colliding_seeds = {
        field for field in seed_fields
        if isinstance(field, str) and _field_leaf(field) in derived_leaves
    }
    if colliding_seeds - set(allowed) and not (set(seed_fields) & set(derived_fields)):
        return [f"fixture {scenario_id} directly seeds semantically derived fields"]
    return []


def _field_leaf(field: str) -> str:
    return field.rsplit(".", 1)[-1]


def _harness_seed_boundary_errors(
    scenario_id: object, seed_fields: object, fixture: dict[str, object],
) -> list[str]:
    if fixture.get("test_kind") not in {"subsystem_state_machine", "typed_query_view"}:
        return []
    prefixes = fixture.get("harness_input_prefixes")
    if not isinstance(prefixes, list) or not prefixes or any(
        not isinstance(prefix, str) or not prefix for prefix in prefixes
    ):
        return [f"fixture {scenario_id} must define harness input prefixes"]
    if not isinstance(seed_fields, list) or any(
        not isinstance(field, str) or field.split(".", 1)[0] not in prefixes
        for field in seed_fields
    ):
        return [f"fixture {scenario_id} seeds outside its harness boundary"]
    return []


def _expected_manifest_errors(scenario_id: object, path_value: object) -> list[str]:
    path = PROJECT_ROOT / path_value if isinstance(path_value, str) else None
    if path is None or not path.is_file():
        return [f"fixture {scenario_id} has a missing expected manifest"]
    expected_namespace = PHASE3_NAMESPACE if "validation\\expected\\phase3" in str(path) or "validation/expected/phase3" in str(path).replace("\\", "/") else "baseline"
    expected_root = PROJECT_ROOT / "validation" / "expected"
    if expected_namespace == PHASE3_NAMESPACE:
        expected_root /= PHASE3_NAMESPACE
    try:
        expected = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"fixture {scenario_id} expected manifest is invalid JSON: {type(exc).__name__}"]
    if not isinstance(expected, dict):
        return [f"fixture {scenario_id} expected manifest has an unsupported shape"]
    if not _is_relative_to(path, expected_root):
        return [f"fixture {scenario_id} crosses the expected manifest namespace"]
    if expected.get("contract") != EXPECTED_CONTRACT:
        return [f"fixture {scenario_id} expected manifest has an unsupported contract"]
    if expected.get("scenario_id") != scenario_id:
        return [f"fixture {scenario_id} expected manifest has a mismatched scenario"]
    assertions = expected.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        return [f"fixture {scenario_id} expected manifest must define assertions"]
    if any(not isinstance(assertion, str) or not assertion.strip() for assertion in assertions):
        return [f"fixture {scenario_id} expected manifest has an invalid assertion"]
    if len(set(assertions)) != len(assertions):
        return [f"fixture {scenario_id} expected manifest has duplicate assertions"]
    return []


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def verify_fixture_documents(
    documents: list[FixtureDocument], scenarios: list[dict[str, object]] | None = None,
) -> dict[str, list[str]]:
    """Validate discovered documents while keeping baseline and Phase 3 separate."""
    baseline = [document.payload for document in documents if document.namespace == "baseline"]
    phase3 = [document.payload for document in documents if document.namespace == PHASE3_NAMESPACE]
    errors: list[str] = []
    expected_paths: set[Path] = set()
    fixture_paths: set[Path] = set()
    fixture_ids: set[str] = set()
    for document in documents:
        resolved_fixture_path = document.path.resolve()
        if resolved_fixture_path in fixture_paths:
            errors.append(f"duplicate fixture path: {_display_path(document.path)}")
        fixture_paths.add(resolved_fixture_path)
        scenario_id = document.payload.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id in fixture_ids:
            errors.append(f"duplicate fixture scenario id: {scenario_id}")
        if isinstance(scenario_id, str):
            fixture_ids.add(scenario_id)
        expected_value = document.payload.get("expected_manifest_path")
        if isinstance(expected_value, str):
            expected_path = (PROJECT_ROOT / expected_value).resolve()
            if expected_path in expected_paths:
                errors.append(f"duplicate expected manifest path: {expected_value}")
            expected_paths.add(expected_path)
        expected_namespace = PHASE3_NAMESPACE if document.namespace == PHASE3_NAMESPACE else "baseline"
        expected_text = str(expected_value).replace("\\", "/") if isinstance(expected_value, str) else ""
        if expected_namespace == PHASE3_NAMESPACE and not expected_text.startswith("validation/expected/phase3/"):
            errors.append(f"fixture {document.payload.get('scenario_id')} crosses the expected manifest namespace")
        if expected_namespace == "baseline" and expected_text.startswith("validation/expected/phase3/"):
            errors.append(f"fixture {document.payload.get('scenario_id')} crosses the expected manifest namespace")
    return {
        "document": errors,
        "baseline": errors + verify_fixtures(baseline, scenarios),
        "phase3": errors + verify_phase3_fixtures(phase3, scenarios),
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def main() -> int:
    fixtures = load_fixtures()
    errors = verify_fixtures(fixtures)
    print(json.dumps({"valid": not errors, "errors": errors, "fixture_count": len(fixtures)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
