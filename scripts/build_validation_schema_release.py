"""
File: build_validation_schema_release.py
Description: 由唯一 schema assembly 組裝可審核的 validation SQL release。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH,
    TRIM_NORMAL_SQL_LINE_TAILS_V1,
    load_manifest,
    selected_schema_parts,
    verify_manifest,
)


DATABASE_TOKEN = "__LU_TEST_DATABASE__"


def release_output_path(manifest: dict[str, object]) -> Path:
    full_release = manifest["full_release"]
    return PROJECT_ROOT / str(full_release["path"])


def build_release_text(manifest: dict[str, object]) -> str:
    _require_valid_manifest(manifest)
    base_schema = manifest["base_schema"]
    base_text = (PROJECT_ROOT / str(base_schema["path"])).read_text(encoding="utf-8")
    base_text = base_text.replace("union_db", DATABASE_TOKEN)
    part_paths = selected_schema_parts(manifest)
    policy = manifest["full_release"].get("source_line_whitespace")
    sections = [_release_header(manifest), _source_section("db/schema.sql", base_text, policy)]
    for part_path in part_paths:
        relative_path = part_path.relative_to(PROJECT_ROOT).as_posix()
        sections.append(_source_section(relative_path, part_path.read_text(encoding="utf-8"), policy))
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


def _source_section(relative_path: str, sql_text: str, policy: str | None = None) -> str:
    # Keep the original section EOF rule and legacy bytes when no policy is set.
    rendered = sql_text.rstrip()
    if policy == TRIM_NORMAL_SQL_LINE_TAILS_V1:
        rendered = _trim_normal_sql_line_tails(rendered)
    elif policy is not None:
        raise ValueError("unsupported full release source whitespace policy")
    return f"-- BEGIN SOURCE: {relative_path}\n{rendered}\n-- END SOURCE: {relative_path}\n"


def _trim_normal_sql_line_tails(text: str) -> str:
    """Trim ASCII line tails outside SQL quotes/comments; never interpret SQL."""
    output: list[str] = []
    state = "normal"
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if state == "line_comment":
            output.append(character)
            if character in "\r\n":
                state = "normal"
        elif state == "block_comment":
            output.append(character)
            if character == "*" and next_character == "/":
                output.append(next_character)
                index += 1
                state = "normal"
        elif state != "normal":
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == state:
                if next_character == state:
                    output.append(next_character)
                    index += 1
                else:
                    state = "normal"
        elif character in "\r\n":
            while output and output[-1] in (" ", "\t"):
                output.pop()
            output.append(character)
        elif character in "'\"`":
            state = character
            output.append(character)
        elif character == "#" or (
            character == "-" and next_character == "-"
            and (index + 2 == len(text) or text[index + 2].isspace())
        ):
            state = "line_comment"
            output.append(character)
        elif character == "/" and next_character == "*":
            state = "block_comment"
            output.extend((character, next_character))
            index += 1
        else:
            output.append(character)
        index += 1
    if state == "normal":
        while output and output[-1] in (" ", "\t"):
            output.pop()
    return "".join(output)


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
