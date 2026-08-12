"""Build the reviewable full-SQL artifact from the versioned schema sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH,
    load_manifest,
    ordered_schema_parts,
    verify_manifest,
)


DATABASE_TOKEN = "__LU_TEST_DATABASE__"


def release_output_path(manifest: dict[str, object]) -> Path:
    full_release = manifest["full_release"]
    return PROJECT_ROOT / str(full_release["path"])


def build_release_text(manifest: dict[str, object]) -> str:
    _require_valid_manifest(manifest)
    base_schema = manifest["base_schema"]
    schema_parts = manifest["schema_parts"]
    base_text = (PROJECT_ROOT / str(base_schema["path"])).read_text(encoding="utf-8")
    base_text = base_text.replace("union_db", DATABASE_TOKEN)
    part_paths = ordered_schema_parts(PROJECT_ROOT / str(schema_parts["directory"]))
    sections = [_release_header(manifest), _source_section("db/schema.sql", base_text)]
    for part_path in part_paths:
        relative_path = part_path.relative_to(PROJECT_ROOT).as_posix()
        sections.append(_source_section(relative_path, part_path.read_text(encoding="utf-8")))
    return "\n".join(sections)


def write_release(manifest: dict[str, object], output_path: Path | None = None) -> Path:
    target_path = output_path or release_output_path(manifest)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(build_release_text(manifest), encoding="utf-8", newline="\n")
    return target_path


def verify_release(manifest: dict[str, object], output_path: Path | None = None) -> list[str]:
    target_path = output_path or release_output_path(manifest)
    if not target_path.is_file():
        return [f"full release artifact is missing: {target_path}"]
    if target_path.read_text(encoding="utf-8") != build_release_text(manifest):
        return ["full release artifact differs from versioned schema sources"]
    return []


def _require_valid_manifest(manifest: dict[str, object]) -> None:
    errors = verify_manifest(manifest)
    if errors:
        raise RuntimeError("validation schema manifest failed: " + "; ".join(errors))


def _release_header(manifest: dict[str, object]) -> str:
    return "\n".join(
        [
            "-- GENERATED FILE. Do not edit by hand.",
            f"-- Release: {manifest['release_id']}",
            f"-- Replace {DATABASE_TOKEN} with an explicitly confirmed lu_test_* database.",
            "-- Rebuild with: python scripts/build_validation_schema_release.py",
            "",
        ]
    )


def _source_section(relative_path: str, sql_text: str) -> str:
    return f"-- BEGIN SOURCE: {relative_path}\n{sql_text.rstrip()}\n-- END SOURCE: {relative_path}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    manifest = load_manifest(arguments.manifest)
    output_path = arguments.output
    if arguments.check:
        errors = verify_release(manifest, output_path)
        if errors:
            raise SystemExit("; ".join(errors))
        return 0
    print(write_release(manifest, output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
