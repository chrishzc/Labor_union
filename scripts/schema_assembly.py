"""
File: schema_assembly.py
Description: 載入並驗證唯一的 fresh schema 組裝 catalog，供 bootstrap 與驗證共用。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSEMBLY_PATH = (
    PROJECT_ROOT / "db" / "schema_assembly" / "labor_union_fresh_schema_v1.json"
)
VALID_CLASSIFICATIONS = frozenset({"active-bootstrap", "migration-only", "retired"})
RETIREMENT_CONTRACT_FIELDS = frozenset(
    {
        "data_effect",
        "replay",
        "rollback",
        "source_object",
        "successor",
        "terminal_schema_evidence",
        "unresolved_policy",
    }
)


@dataclass(frozen=True)
class SchemaAssembly:
    assembly_id: str
    base_schema_path: Path
    active_artifact_paths: tuple[Path, ...]
    classifications: dict[str, str]


def load_schema_assembly(path: Path = DEFAULT_ASSEMBLY_PATH) -> SchemaAssembly:
    raw = _read_catalog(path)
    _validate_catalog(raw, path)
    active_paths = tuple(
        PROJECT_ROOT / relative_path for relative_path in raw["active_bootstrap"]
    )
    classifications = _classifications(raw)
    _verify_active_digest(raw, active_paths)
    return SchemaAssembly(
        assembly_id=str(raw["assembly_id"]),
        base_schema_path=PROJECT_ROOT / str(raw["base_schema"]["path"]),
        active_artifact_paths=active_paths,
        classifications=classifications,
    )


def validate_schema_assembly(path: Path = DEFAULT_ASSEMBLY_PATH) -> list[str]:
    try:
        load_schema_assembly(path)
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        return [str(error)]
    return []


def _read_catalog(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def _validate_catalog(raw: dict[str, Any], path: Path) -> None:
    if raw.get("contract") != "labor-union-schema-assembly/v1":
        raise ValueError("schema assembly contract is invalid")
    if not isinstance(raw.get("assembly_id"), str) or not raw["assembly_id"]:
        raise ValueError("schema assembly id is missing")
    _validate_base_schema(raw)
    classifications = _classifications(raw)
    _validate_classified_paths(classifications)
    _validate_active_paths(raw, classifications)
    _validate_retirement_contracts(raw, classifications)
    _validate_catalog_coverage(classifications, path)


def _validate_base_schema(raw: dict[str, Any]) -> None:
    base_schema = raw.get("base_schema")
    if not isinstance(base_schema, dict):
        raise ValueError("schema assembly base schema is missing")
    base_path = PROJECT_ROOT / str(base_schema.get("path") or "")
    if not base_path.is_file():
        raise ValueError("schema assembly base schema is missing")
    expected_hash = str(base_schema.get("sha256") or "")
    if _sha256(base_path) != expected_hash:
        raise ValueError("schema assembly base schema digest differs")


def _classifications(raw: dict[str, Any]) -> dict[str, str]:
    non_active = raw.get("classifications")
    active_paths = raw.get("active_bootstrap")
    if not isinstance(non_active, dict) or not isinstance(active_paths, list):
        raise ValueError("schema assembly classifications are missing")
    classifications = {str(path): "active-bootstrap" for path in active_paths}
    classifications.update({str(path): str(status) for path, status in non_active.items()})
    return classifications


def _validate_classified_paths(classifications: dict[str, str]) -> None:
    if not classifications:
        raise ValueError("schema assembly classifications are empty")
    invalid = sorted(set(classifications.values()) - VALID_CLASSIFICATIONS)
    if invalid:
        raise ValueError(f"schema assembly classifications are invalid: {', '.join(invalid)}")
    for relative_path in classifications:
        if not relative_path.startswith("db/schema_parts/"):
            raise ValueError("schema assembly path escapes schema_parts")
        if not (PROJECT_ROOT / relative_path).is_file():
            raise ValueError(f"schema assembly artifact is missing: {relative_path}")


def _validate_active_paths(raw: dict[str, Any], classifications: dict[str, str]) -> None:
    active_paths = raw.get("active_bootstrap")
    if not isinstance(active_paths, list) or not active_paths:
        raise ValueError("schema assembly active bootstrap is missing")
    if len(active_paths) != len(set(active_paths)):
        raise ValueError("schema assembly active bootstrap contains duplicates")
    active_set = {str(path) for path in active_paths}
    expected = {path for path, status in classifications.items() if status == "active-bootstrap"}
    if active_set != expected:
        raise ValueError("schema assembly active bootstrap differs from classifications")


def _validate_retirement_contracts(
    raw: dict[str, Any], classifications: dict[str, str]
) -> None:
    contracts = raw.get("retirement_contracts")
    if not isinstance(contracts, dict):
        raise ValueError("schema assembly retirement contracts are missing")
    removed_paths = {
        path
        for path, status in classifications.items()
        if status in {"migration-only", "retired"}
    }
    if set(contracts) != removed_paths:
        raise ValueError("schema assembly retirement contracts differ from removed artifacts")
    for artifact_path, contract in contracts.items():
        if not isinstance(contract, dict) or set(contract) != RETIREMENT_CONTRACT_FIELDS:
            raise ValueError(f"schema assembly retirement contract is invalid: {artifact_path}")
        if any(not isinstance(value, str) or not value.strip() for value in contract.values()):
            raise ValueError(f"schema assembly retirement contract is incomplete: {artifact_path}")


def _validate_catalog_coverage(classifications: dict[str, str], path: Path) -> None:
    filesystem_paths = {
        schema_path.relative_to(PROJECT_ROOT).as_posix()
        for schema_path in (PROJECT_ROOT / "db" / "schema_parts").glob("*.sql")
    }
    if filesystem_paths != set(classifications):
        raise ValueError("schema assembly does not classify every schema part")
    if not path.is_file():
        raise ValueError("schema assembly catalog is missing")


def _verify_active_digest(raw: dict[str, Any], active_paths: tuple[Path, ...]) -> None:
    expected_digest = str(raw.get("active_artifacts_sha256") or "")
    actual_digest = _ordered_digest(active_paths)
    if actual_digest != expected_digest:
        raise ValueError(
            "schema assembly active artifact digest differs: "
            f"expected={expected_digest} actual={actual_digest}"
        )


def _ordered_digest(paths: tuple[Path, ...]) -> str:
    source = "".join(f"{path.name}:{_sha256(path)}\n" for path in paths)
    return hashlib.sha256(source.encode()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
