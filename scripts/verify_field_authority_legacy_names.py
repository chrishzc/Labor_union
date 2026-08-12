"""Audit retired field names without hiding migration or historical evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "validation" / "field_authority_legacy_name_audit_v1.json"
CONTRACT = "labor-union-field-authority-legacy-name-audit/v1"


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(
    manifest: dict[str, object], project_root: Path = PROJECT_ROOT
) -> list[str]:
    errors: list[str] = []
    if manifest.get("contract") != CONTRACT:
        errors.append("unsupported field-authority audit contract")
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        return errors + ["field-authority audit requires mappings"]
    for mapping in mappings:
        errors.extend(_mapping_errors(mapping, manifest, project_root))
    return errors


def audit_report(
    manifest: dict[str, object], project_root: Path = PROJECT_ROOT
) -> dict[str, object]:
    return {
        "contract": manifest.get("contract"),
        "mappings": [
            _mapping_report(mapping, manifest, project_root)
            for mapping in manifest.get("mappings", [])
        ],
    }


def _mapping_errors(
    mapping: object, manifest: dict[str, object], project_root: Path
) -> list[str]:
    if not isinstance(mapping, dict):
        return ["field-authority audit has a non-object mapping"]
    mapping_id = mapping.get("mapping_id")
    required = ("mapping_id", "legacy_token", "canonical_token", "required_canonical_paths")
    if any(not mapping.get(field) for field in required):
        return [f"field-authority mapping {mapping_id} is incomplete"]
    report = _mapping_report(mapping, manifest, project_root)
    errors = [
        f"field-authority mapping {mapping_id} has unexpected legacy references"
        for _ in report["unexpected_legacy_references"]
    ]
    errors.extend(
        f"field-authority mapping {mapping_id} lacks canonical token in {path}"
        for path in report["missing_canonical_paths"]
    )
    return errors


def _mapping_report(
    mapping: dict[str, object], manifest: dict[str, object], project_root: Path
) -> dict[str, object]:
    legacy_token = str(mapping.get("legacy_token", ""))
    canonical_token = str(mapping.get("canonical_token", ""))
    allowed_paths = set(mapping.get("allowed_legacy_paths", []))
    legacy_references = _token_references(
        legacy_token, _mapping_scan_scope(mapping, manifest), project_root
    )
    unexpected = [
        reference
        for reference in legacy_references
        if not _is_allowed(reference["path"], allowed_paths)
    ]
    required_paths = mapping.get("required_canonical_paths", [])
    missing_canonical = [
        path for path in required_paths if not _path_contains(path, canonical_token, project_root)
    ]
    return {
        "mapping_id": mapping.get("mapping_id"),
        "legacy_token": legacy_token,
        "canonical_token": canonical_token,
        "allowed_legacy_references": [
            reference for reference in legacy_references if reference not in unexpected
        ],
        "unexpected_legacy_references": unexpected,
        "missing_canonical_paths": missing_canonical,
    }


def _mapping_scan_scope(
    mapping: dict[str, object], manifest: dict[str, object]
) -> dict[str, object]:
    scope = dict(manifest)
    for field in ("scan_roots", "scan_extensions", "excluded_paths"):
        if field in mapping:
            scope[field] = mapping[field]
    return scope


def _token_references(
    token: str, manifest: dict[str, object], project_root: Path
) -> list[dict[str, object]]:
    roots = manifest.get("scan_roots", [])
    extensions = set(manifest.get("scan_extensions", []))
    excluded_paths = set(manifest.get("excluded_paths", []))
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    references: list[dict[str, object]] = []
    for root_name in roots:
        root = project_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in extensions:
                continue
            relative_path = path.relative_to(project_root).as_posix()
            if _is_allowed(relative_path, excluded_paths):
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    references.append({"path": relative_path, "line": line_number})
    return references


def _is_allowed(path: object, allowed_paths: set[object]) -> bool:
    if not isinstance(path, str):
        return False
    return any(
        isinstance(allowed, str)
        and (path == allowed or allowed.endswith("/") and path.startswith(allowed))
        for allowed in allowed_paths
    )


def _path_contains(path_text: object, token: str, project_root: Path) -> bool:
    path = project_root / path_text if isinstance(path_text, str) else None
    return bool(path and path.is_file() and re.search(rf"\b{re.escape(token)}\b", path.read_text(encoding="utf-8")))


def main() -> int:
    manifest = load_manifest()
    errors = verify_manifest(manifest)
    print(json.dumps({"valid": not errors, "errors": errors, "report": audit_report(manifest)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
