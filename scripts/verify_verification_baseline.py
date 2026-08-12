"""Fail-closed validation and coverage reporting for the dual-track verification baseline."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_PATH = PROJECT_ROOT / "validation" / "verification_baseline_v1.json"
TRACK_POLICIES = {
    "A": "roots_and_external_inputs_only",
    "B": "non_business_harness_only",
}
TEST_KINDS = {
    "domain_root_data",
    "external_input_fixture",
    "subsystem_state_machine",
    "typed_query_view",
    "expected_manifest",
    "metadata_fixture",
    "filesystem_artifact",
    "process_network_harness",
    "benchmark_evidence",
    "manual_environment_acceptance",
}
TRACK_TEST_KINDS = {
    "A": {
        "domain_root_data", "external_input_fixture", "subsystem_state_machine",
        "typed_query_view", "expected_manifest",
    },
    "B": {
        "metadata_fixture",
        "filesystem_artifact",
        "process_network_harness",
        "benchmark_evidence",
        "manual_environment_acceptance",
    },
}
STATUSES = {"specified", "gap", "complete"}


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_baseline(baseline: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if baseline.get("contract") != "labor-union-verification-baseline/v1":
        errors.append("unsupported baseline contract")
    tracks = baseline.get("tracks")
    if not isinstance(tracks, list):
        return errors + ["tracks must be a list"]
    track_ids = [track.get("id") for track in tracks if isinstance(track, dict)]
    if track_ids != ["A", "B"]:
        errors.append("tracks must be ordered A then B")
    suite_ids: set[str] = set()
    for track in tracks:
        errors.extend(_track_errors(track, suite_ids))
    return errors


def coverage_report(baseline: dict[str, object]) -> dict[str, object]:
    tracks = baseline["tracks"]
    track_reports = []
    for track in tracks:
        suites = track["suites"]
        status_counts = Counter(suite["status"] for suite in suites)
        track_reports.append(
            {
                "track": track["id"],
                "suite_count": len(suites),
                "status_counts": dict(sorted(status_counts.items())),
                "gaps": [suite["id"] for suite in suites if suite["status"] == "gap"],
                "complete": all(suite["status"] == "complete" for suite in suites),
            }
        )
    return {
        "release_id": baseline["release_id"],
        "tracks": track_reports,
        "overall_complete": all(track["complete"] for track in track_reports),
    }


def _track_errors(track: object, suite_ids: set[str]) -> list[str]:
    if not isinstance(track, dict):
        return ["track must be an object"]
    track_id = track.get("id")
    errors: list[str] = []
    if track.get("root_input_policy") != TRACK_POLICIES.get(track_id):
        errors.append(f"track {track_id} has an invalid root input policy")
    suites = track.get("suites")
    if not isinstance(suites, list) or not suites:
        return errors + [f"track {track_id} must have suites"]
    for suite in suites:
        errors.extend(_suite_errors(track_id, suite, suite_ids))
    return errors


def _suite_errors(track_id: object, suite: object, suite_ids: set[str]) -> list[str]:
    if not isinstance(suite, dict):
        return [f"track {track_id} has a non-object suite"]
    suite_id = suite.get("id")
    errors: list[str] = []
    if not isinstance(suite_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9]*", suite_id):
        errors.append(f"track {track_id} has invalid suite id")
    elif suite_id in suite_ids:
        errors.append(f"duplicate suite id: {suite_id}")
    else:
        suite_ids.add(suite_id)
    if suite.get("status") not in STATUSES:
        errors.append(f"suite {suite_id} has invalid status")
    _append_required_list_errors(errors, suite, suite_id, "test_kinds", TEST_KINDS)
    _append_track_test_kind_errors(errors, suite, suite_id, track_id)
    _append_required_list_errors(errors, suite, suite_id, "source_refs")
    _append_required_list_errors(errors, suite, suite_id, "acceptance")
    _append_acceptance_completeness_error(errors, suite, suite_id)
    if suite.get("status") == "complete":
        errors.append(f"suite {suite_id} cannot be complete before executable scenario receipts exist")
    return errors


def _append_required_list_errors(
    errors: list[str], suite: dict[str, object], suite_id: object, field: str,
    allowed_values: set[str] | None = None,
) -> None:
    values = suite.get(field)
    if not isinstance(values, list) or not values:
        errors.append(f"suite {suite_id} must define {field}")
        return
    if allowed_values and any(value not in allowed_values for value in values):
        errors.append(f"suite {suite_id} has unsupported {field}")


def _append_track_test_kind_errors(
    errors: list[str], suite: dict[str, object], suite_id: object, track_id: object,
) -> None:
    test_kinds = suite.get("test_kinds")
    allowed_kinds = TRACK_TEST_KINDS.get(track_id, set())
    if not isinstance(test_kinds, list):
        return
    if any(test_kind not in allowed_kinds for test_kind in test_kinds):
        errors.append(f"suite {suite_id} has a test_kind outside track {track_id}")


def _append_acceptance_completeness_error(
    errors: list[str], suite: dict[str, object], suite_id: object,
) -> None:
    acceptance = suite.get("acceptance")
    test_kinds = suite.get("test_kinds")
    if not isinstance(acceptance, list) or not isinstance(test_kinds, list):
        return
    if len(acceptance) < len(test_kinds):
        errors.append(f"suite {suite_id} has incomplete acceptance criteria")


def main() -> int:
    baseline = load_baseline()
    errors = verify_baseline(baseline)
    result = {"valid": not errors, "errors": errors, "coverage": coverage_report(baseline)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
