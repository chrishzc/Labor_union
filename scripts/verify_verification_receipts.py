"""Validate immutable-looking receipts without allowing them to imply missing coverage."""

from __future__ import annotations

import json
import re
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_verification_scenarios import (
    DEFAULT_SCENARIO_DIRECTORY,
    load_scenarios,
)


DEFAULT_RECEIPT_DIRECTORY = PROJECT_ROOT / "validation" / "receipts"
RECEIPT_CONTRACT = "labor-union-verification-receipt/v1"
_PERSISTENT_DATABASE_FORBIDDEN_PATTERNS = (
    r"\bDROP\s+DATABASE\b",
    r"\bTRUNCATE\s+(?:TABLE\s+)?",
    r"\bDELETE\s+FROM\b",
    r"\bbootstrap\s*\(",
)


def load_receipts(directory: Path = DEFAULT_RECEIPT_DIRECTORY) -> list[dict[str, object]]:
    if not directory.is_dir():
        return []
    return [
        receipt
        for path in sorted(directory.glob("*.json"))
        for receipt in [json.loads(path.read_text(encoding="utf-8"))]
        if receipt.get("contract") == RECEIPT_CONTRACT
    ]


def verify_receipts(
    receipts: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> list[str]:
    scenarios = scenarios or load_scenarios(DEFAULT_SCENARIO_DIRECTORY)
    scenario_ids = {scenario["scenario_id"] for scenario in scenarios}
    scenarios_by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    scenario_digests = _scenario_digests()
    receipt_ids: set[str] = set()
    errors: list[str] = []
    for receipt in receipts:
        errors.extend(
            _receipt_errors(
                receipt, scenario_ids, scenarios_by_id, scenario_digests, receipt_ids
            )
        )
    return errors


def receipt_coverage_report(
    receipts: list[dict[str, object]], scenarios: list[dict[str, object]] | None = None
) -> dict[str, object]:
    scenarios = scenarios or load_scenarios(DEFAULT_SCENARIO_DIRECTORY)
    passed_ids = {
        receipt["scenario_id"]
        for receipt in receipts
        if receipt.get("result") == "passed"
    }
    scenario_ids = {scenario["scenario_id"] for scenario in scenarios}
    return {
        "receipt_count": len(receipts),
        "passed_scenario_ids": sorted(passed_ids),
        "scenarios_without_passing_receipt": sorted(scenario_ids - passed_ids),
        "all_scenarios_verified": scenario_ids == passed_ids,
    }


def _receipt_errors(
    receipt: dict[str, object], scenario_ids: set[str],
    scenarios_by_id: dict[str, dict[str, object]], scenario_digests: dict[str, str],
    receipt_ids: set[str],
) -> list[str]:
    scenario_id = receipt.get("scenario_id")
    errors: list[str] = []
    if receipt.get("contract") != RECEIPT_CONTRACT:
        errors.append(f"receipt {scenario_id} has an unsupported contract")
    if scenario_id not in scenario_ids:
        errors.append(f"receipt {scenario_id} references an unknown scenario")
    elif scenario_id in receipt_ids:
        errors.append(f"duplicate receipt for scenario: {scenario_id}")
    else:
        receipt_ids.add(scenario_id)
    if receipt.get("result") not in {"passed", "failed"}:
        errors.append(f"receipt {scenario_id} has an invalid result")
    scenario = scenarios_by_id.get(scenario_id)
    if receipt.get("result") == "passed" and scenario is not None:
        if scenario.get("status") != "bound":
            errors.append(f"receipt {scenario_id} cannot pass an unbound scenario")
        execution = scenario.get("execution")
        if not isinstance(execution, dict) or receipt.get("runner") != execution.get("runner"):
            errors.append(f"receipt {scenario_id} runner does not match scenario binding")
        errors.extend(_database_target_errors(scenario_id, scenario, receipt.get("environment")))
        errors.extend(_persistent_database_source_errors(scenario_id, scenario))
    if not isinstance(receipt.get("assertion_count"), int) or receipt["assertion_count"] < 1:
        errors.append(f"receipt {scenario_id} must report positive assertion_count")
    if not isinstance(receipt.get("runner"), list) or not receipt["runner"]:
        errors.append(f"receipt {scenario_id} must record its runner")
    if not isinstance(receipt.get("environment"), dict) or not receipt["environment"]:
        errors.append(f"receipt {scenario_id} must record its environment")
    if receipt.get("scenario_digest") != scenario_digests.get(scenario_id):
        errors.append(f"receipt {scenario_id} has a stale or missing scenario digest")
    _digest_mapping_errors(errors, scenario_id, receipt.get("input_digests"))
    errors.extend(_input_path_errors(scenario_id, receipt.get("input_paths"), receipt.get("input_digests")))
    return errors


def _scenario_digests() -> dict[str, str]:
    return {
        path.stem: _source_aware_scenario_digest(path)
        for path in DEFAULT_SCENARIO_DIRECTORY.glob("*.json")
    }


def _source_aware_scenario_digest(scenario_path: Path) -> str:
    digest = hashlib.sha256(scenario_path.read_bytes())
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    for source_ref in sorted(scenario.get("source_refs", [])):
        digest.update(b"\0")
        digest.update(str(source_ref).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_source_reference_bytes(source_ref))
    return digest.hexdigest()


def _database_target_errors(
    scenario_id: object, scenario: dict[str, object], environment: object,
) -> list[str]:
    if scenario.get("status") != "bound" or scenario.get("requires_database") is not True:
        return []
    if not isinstance(environment, dict):
        return []
    database = environment.get("database")
    if isinstance(database, str) and database.startswith("lu_test_"):
        return []
    return [f"receipt {scenario_id} must use a lu_test_* database"]


def _persistent_database_source_errors(
    scenario_id: object, scenario: dict[str, object], project_root: Path = PROJECT_ROOT,
) -> list[str]:
    if scenario.get("database_execution_mode") != "persistent_append_only":
        return []
    execution = scenario.get("execution")
    if not isinstance(execution, dict):
        return []
    test_paths = execution.get("test_paths")
    if not isinstance(test_paths, list):
        return []
    return _unsafe_persistent_source_errors(scenario_id, test_paths, project_root)


def _unsafe_persistent_source_errors(
    scenario_id: object, test_paths: list[object], project_root: Path,
) -> list[str]:
    errors: list[str] = []
    for test_path in test_paths:
        source_path = project_root / test_path if isinstance(test_path, str) else None
        if source_path is None or not source_path.is_file():
            continue
        source = source_path.read_text(encoding="utf-8")
        if not _has_explicit_persistent_target_guard(source):
            errors.append(f"receipt {scenario_id} persistent test lacks an explicit database guard")
        if any(re.search(pattern, source, re.IGNORECASE) for pattern in _PERSISTENT_DATABASE_FORBIDDEN_PATTERNS):
            errors.append(f"receipt {scenario_id} persistent test contains a destructive database operation")
    return errors


def _has_explicit_persistent_target_guard(source: str) -> bool:
    has_environment_guard = (
        "LABOR_UNION_TEST_MYSQL_DATABASE" in source
        and 'os.getenv("DB_DATABASE") != DATABASE' in source
    )
    has_explicit_adapter_target = '"database": DATABASE' in source
    return has_environment_guard or has_explicit_adapter_target


def _source_reference_bytes(source_ref: object) -> bytes:
    if not isinstance(source_ref, str):
        return b"<invalid-source-reference>"
    path = PROJECT_ROOT / source_ref.split("#", 1)[0]
    if not path.is_file():
        return b"<missing-source-reference>"
    return path.read_bytes()


def _digest_mapping_errors(
    errors: list[str], scenario_id: object, input_digests: object
) -> None:
    if not isinstance(input_digests, dict) or not input_digests:
        errors.append(f"receipt {scenario_id} must record input digests")
        return
    if any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in input_digests.values()):
        errors.append(f"receipt {scenario_id} has an invalid input digest")


def _input_path_errors(
    scenario_id: object, input_paths: object, input_digests: object
) -> list[str]:
    if not isinstance(input_paths, dict) or not input_paths:
        return [f"receipt {scenario_id} must record input paths"]
    if not isinstance(input_digests, dict) or set(input_paths) != set(input_digests):
        return [f"receipt {scenario_id} input paths and digests differ"]
    for label, path_value in input_paths.items():
        path = PROJECT_ROOT / path_value if isinstance(path_value, str) else None
        if path is None or not path.is_file():
            return [f"receipt {scenario_id} has a missing input path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != input_digests[label]:
            return [f"receipt {scenario_id} has a stale input digest"]
    return []


def main() -> int:
    receipts = load_receipts()
    errors = verify_receipts(receipts)
    print(json.dumps({"valid": not errors, "errors": errors, "coverage": receipt_coverage_report(receipts)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
