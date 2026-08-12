"""Validate root-data fixtures and independent expected manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_verification_scenarios import load_scenarios


DEFAULT_FIXTURE_DIRECTORY = PROJECT_ROOT / "validation" / "fixtures"
FIXTURE_CONTRACT = "labor-union-verification-fixture/v1"
EXPECTED_CONTRACT = "labor-union-verification-expected/v1"


def load_fixtures(directory: Path = DEFAULT_FIXTURE_DIRECTORY) -> list[dict[str, object]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


def verify_fixtures(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> list[str]:
    scenarios = scenarios or load_scenarios()
    scenario_test_kinds = {
        scenario["scenario_id"]: set(scenario["test_kinds"])
        for scenario in scenarios
    }
    scenario_tracks = {
        scenario["scenario_id"]: scenario["track"]
        for scenario in scenarios
    }
    fixture_scenario_ids: set[object] = set()
    errors: list[str] = []
    for fixture in fixtures:
        errors.extend(
            _fixture_errors(
                fixture,
                scenario_test_kinds,
                scenario_tracks,
                fixture_scenario_ids,
            )
        )
    missing = {
        scenario_id
        for scenario_id, track in scenario_tracks.items()
        if track == "A"
    } - fixture_scenario_ids
    if missing:
        errors.append(f"missing fixtures for A scenarios: {', '.join(sorted(missing))}")
    return errors


def fixture_coverage_report(
    fixtures: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> dict[str, object]:
    scenarios = scenarios or load_scenarios()
    required_scenarios = {
        scenario["scenario_id"]
        for scenario in scenarios
        if scenario["track"] == "A"
    }
    fixture_scenarios = {fixture.get("scenario_id") for fixture in fixtures}
    return {
        "fixture_count": len(fixtures),
        "required_a_scenario_count": len(required_scenarios),
        "scenarios_without_fixture": sorted(required_scenarios - fixture_scenarios),
        "all_a_scenarios_have_fixture": required_scenarios <= fixture_scenarios,
    }


def _fixture_errors(
    fixture: dict[str, object], scenario_test_kinds: dict[str, set[str]],
    scenario_tracks: dict[str, object], fixture_scenario_ids: set[object],
) -> list[str]:
    scenario_id = fixture.get("scenario_id")
    errors: list[str] = []
    if fixture.get("contract") != FIXTURE_CONTRACT:
        errors.append(f"fixture {scenario_id} has an unsupported contract")
    if scenario_tracks.get(scenario_id) != "A":
        errors.append(f"fixture {scenario_id} must reference an A scenario")
    elif scenario_id in fixture_scenario_ids:
        errors.append(f"duplicate fixture scenario id: {scenario_id}")
    else:
        fixture_scenario_ids.add(scenario_id)
    if fixture.get("test_kind") not in scenario_test_kinds.get(scenario_id, set()):
        errors.append(f"fixture {scenario_id} has an unapproved test_kind")
    if fixture.get("test_kind") not in {
        "domain_root_data", "external_input_fixture", "subsystem_state_machine",
        "typed_query_view",
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
    expected = json.loads(path.read_text(encoding="utf-8"))
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


def main() -> int:
    fixtures = load_fixtures()
    errors = verify_fixtures(fixtures)
    print(json.dumps({"valid": not errors, "errors": errors, "fixture_count": len(fixtures)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
