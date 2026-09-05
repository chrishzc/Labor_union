"""
File: verify_validation_schema_manifest.py
Description: 驗證 validation schema manifest及依順序套用後的最終資料庫物件。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

from scripts.schema_assembly import load_schema_assembly


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT / "db" / "cutover_releases" / "labor_union_validation_schema_v1.json"
)


def load_manifest(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, object]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def schema_part_sort_key(path: Path) -> tuple[int, str, str]:
    if path.name == "179_line_identity_canonical_menu_publication.sql":
        return 186, "z", path.name
    match = re.match(r"^(\d+)([a-z]*)_", path.name, re.IGNORECASE)
    if match:
        return int(match.group(1)), match.group(2).lower(), path.name
    return 10**9, "", path.name


def ordered_schema_parts(schema_parts_directory: Path) -> list[Path]:
    return sorted(schema_parts_directory.glob("*.sql"), key=schema_part_sort_key)


def selected_schema_parts(
    manifest: dict[str, object], project_root: Path = PROJECT_ROOT
) -> list[Path]:
    assembly_ref = manifest["schema_assembly"]
    assembly_path = project_root / str(assembly_ref["path"])
    expected_digest = str(assembly_ref["sha256"])
    actual_digest = sha256_file(assembly_path)
    if actual_digest != expected_digest:
        raise ValueError(
            "schema assembly digest differs from validation manifest: "
            f"expected={expected_digest} actual={actual_digest}"
        )
    assembly = load_schema_assembly(assembly_path)
    return list(assembly.active_artifact_paths)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordered_parts_digest(schema_parts: list[Path]) -> str:
    digest = hashlib.sha256()
    for schema_part in schema_parts:
        digest.update(f"{schema_part.name}:{sha256_file(schema_part)}\n".encode())
    return digest.hexdigest()


def verify_manifest(manifest: dict[str, object], project_root: Path = PROJECT_ROOT) -> list[str]:
    base_schema = manifest["base_schema"]
    base_path = project_root / str(base_schema["path"])
    errors = _base_schema_errors(base_path, base_schema)
    try:
        parts = selected_schema_parts(manifest, project_root)
    except (KeyError, OSError, ValueError) as error:
        return [*errors, str(error)]
    errors.extend(_schema_part_errors(parts, manifest["schema_parts"]))
    return errors


def expected_database_objects(
    manifest: dict[str, object], project_root: Path = PROJECT_ROOT
) -> dict[str, set[str]]:
    """Return the tables, views, and triggers declared by this release."""
    base_schema = manifest["base_schema"]
    artifact_paths = [project_root / str(base_schema["path"])]
    artifact_paths.extend(selected_schema_parts(manifest, project_root))
    return _effective_database_objects(artifact_paths)


def verify_database_objects(cursor, database: str, expected: dict[str, set[str]]) -> list[str]:
    """Compare an already-created database with objects declared by the release."""
    actual = {
        "tables": _database_object_names(cursor, database, "BASE TABLE"),
        "views": _database_object_names(cursor, database, "VIEW"),
        "triggers": _database_trigger_names(cursor, database),
    }
    return _missing_object_errors(expected, actual)


def _base_schema_errors(base_path: Path, base_schema: dict[str, object]) -> list[str]:
    if not base_path.is_file():
        return [f"base schema is missing: {base_path}"]
    if sha256_file(base_path) != base_schema["sha256"]:
        return ["base schema digest differs from manifest"]
    return []


def _schema_part_errors(parts: list[Path], schema_parts: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if len(parts) != schema_parts["expected_count"]:
        errors.append("schema part count differs from manifest")
    if ordered_parts_digest(parts) != schema_parts["ordered_digest_sha256"]:
        errors.append("ordered schema part digest differs from manifest")
    if not parts or parts[-1].name != schema_parts["terminal_artifact"]:
        errors.append("terminal schema artifact differs from manifest")
    return errors


_TABLE_PATTERN = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_VIEW_PATTERN = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_TRIGGER_PATTERN = re.compile(
    r"\bCREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_DROP_TABLE_PATTERN = re.compile(
    r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_DROP_VIEW_PATTERN = re.compile(
    r"\bDROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_DROP_TRIGGER_PATTERN = re.compile(
    r"\bDROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_TRIGGER_TARGET_PATTERN = re.compile(
    r"\bCREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?.*?\bON\s+`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE | re.DOTALL,
)


def _effective_database_objects(paths: Iterable[Path]) -> dict[str, set[str]]:
    objects = {"tables": set(), "views": set(), "triggers": set()}
    trigger_targets: dict[str, str] = {}
    for path in paths:
        _apply_object_events(path.read_text(encoding="utf-8"), objects, trigger_targets)
    return objects


def _apply_object_events(sql: str, objects, trigger_targets) -> None:
    events = []
    for kind, operation, pattern in (
        ("tables", "create", _TABLE_PATTERN),
        ("views", "create", _VIEW_PATTERN),
        ("triggers", "create", _TRIGGER_TARGET_PATTERN),
        ("tables", "drop", _DROP_TABLE_PATTERN),
        ("views", "drop", _DROP_VIEW_PATTERN),
        ("triggers", "drop", _DROP_TRIGGER_PATTERN),
    ):
        events.extend((match.start(), kind, operation, match) for match in pattern.finditer(sql))
    for _, kind, operation, match in sorted(events, key=lambda event: event[0]):
        name = match.group(1)
        if operation == "create":
            objects[kind].add(name)
            if kind == "triggers":
                trigger_targets[name] = match.group(2)
            continue
        objects[kind].discard(name)
        if kind == "triggers":
            trigger_targets.pop(name, None)
        if kind == "tables":
            dropped_triggers = {
                trigger for trigger, target in trigger_targets.items() if target == name
            }
            objects["triggers"].difference_update(dropped_triggers)
            for trigger in dropped_triggers:
                trigger_targets.pop(trigger, None)


def _declared_objects(paths: Iterable[Path], pattern: re.Pattern[str]) -> set[str]:
    declared_names: set[str] = set()
    for path in paths:
        declared_names.update(pattern.findall(path.read_text(encoding="utf-8")))
    return declared_names


def _database_object_names(cursor, database: str, table_type: str) -> set[str]:
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = %s",
        (database, table_type),
    )
    return {row[0] for row in cursor.fetchall()}


def _database_trigger_names(cursor, database: str) -> set[str]:
    cursor.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema = %s",
        (database,),
    )
    return {row[0] for row in cursor.fetchall()}


def _missing_object_errors(
    expected: dict[str, set[str]], actual: dict[str, set[str]]
) -> list[str]:
    errors: list[str] = []
    for object_kind, expected_names in expected.items():
        missing_names = sorted(expected_names - actual[object_kind])
        if missing_names:
            errors.append(f"missing {object_kind}: {', '.join(missing_names)}")
    return errors


def main() -> int:
    manifest = load_manifest()
    errors = verify_manifest(manifest)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
