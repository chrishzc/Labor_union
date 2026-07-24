"""Utilities for migrating ADAD task snapshots from schema v2 to v3."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


def _read_task(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_task(path: Path, task: dict[str, Any]) -> None:
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_v3_candidate(task: dict[str, Any], expected_node_name: str | None = None) -> dict[str, Any]:
    """Return a small validation report for a v3 task candidate."""

    errors: list[str] = []

    if task.get("schema_version") != 3:
        errors.append("schema_version must be 3")

    if not isinstance(task.get("task_id"), str) or "@" not in task.get("task_id", ""):
        errors.append("missing or invalid task_id")

    if expected_node_name is not None and task.get("node_name") != expected_node_name:
        errors.append(f"node_name mismatch: {task.get('node_name')} != {expected_node_name}")

    spec = task.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec must be a dict")

    target_node = spec.get("target_node") if isinstance(spec, dict) else None
    if not isinstance(target_node, dict):
        errors.append("spec.target_node must be a dict")
    else:
        if not isinstance(target_node.get("name"), str):
            errors.append("spec.target_node.name must be a string")
        if not isinstance(target_node.get("type"), str):
            errors.append("spec.target_node.type must be a string")

    if not isinstance(task.get("history"), list):
        errors.append("history must be a list")

    return {"valid": len(errors) == 0, "errors": errors}


def _adad_validator(task: dict[str, Any], expected_node_name: str | None = None) -> dict[str, Any]:
    """Validate a migrated task candidate through the local v3 contract."""

    return validate_v3_candidate(task, expected_node_name)


def _require_task_spec(task: dict[str, Any]) -> None:
    if not task.get("task_id"):
        raise ValueError("task has no task_id")


def build_v3_candidate(
    task: dict[str, Any],
    migrated_at: str | None = None,
    validator: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if task.get("schema_version") != 2:
        raise ValueError("Cannot migrate: schema_version=2 is required")

    _require_task_spec(task)

    migrated_at = migrated_at or datetime.now(timezone.utc).isoformat()
    candidate = deepcopy(task)
    candidate["schema_version"] = 3
    history = list(task.get("history", []))
    if not isinstance(history, list):
        raise ValueError("history must be list")
    history.append(
        {
            "event": "schema_v2_to_v3_migrated",
            "at": migrated_at,
            "from_schema_version": 2,
        }
    )
    candidate["history"] = history

    target_node = candidate.setdefault("spec", {}).setdefault("target_node", {})
    target_node.setdefault("non_goals", [])

    if validator is None:
        result = validate_v3_candidate(candidate, task.get("node_name"))
    else:
        result = validator(candidate, task.get("node_name"))

    if not result.get("valid", False):
        raise ValueError((result.get("errors") or ["invalid candidate"])[0])

    return candidate


def _iter_task_paths(tasks_dir: Path) -> Iterable[Path]:
    yield from sorted(p for p in tasks_dir.glob("*.task.json"))


def migrate_tasks(
    tasks_dir: str | Path,
    *,
    apply: bool = False,
    archive_dir: str = ".agents/archive",
    project_root: str | Path = ".",
    migrated_at: str | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    tasks_dir = Path(tasks_dir).resolve()
    if not str(tasks_dir).startswith(str((project_root / ".agents" / "tasks").resolve())):
        raise ValueError("task path must be under .agents/tasks")

    counts: Counter[str] = Counter()
    migrated_count = 0

    for task_path in _iter_task_paths(tasks_dir):
        task = _read_task(task_path)

        schema_version = task.get("schema_version")
        if schema_version == 3:
            counts["skipped"] += 1
            continue
        if schema_version != 2:
            counts["blocked"] += 1
            continue

        try:
            candidate = build_v3_candidate(task, migrated_at=migrated_at)
        except (KeyError, ValueError):
            counts["blocked"] += 1
            continue

        if apply:
            archived_dir = project_root / archive_dir
            archived_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(task_path, archived_dir / task_path.name)
            _write_task(task_path, candidate)
            counts["migrated"] += 1
            migrated_count += 1
        else:
            counts["would_migrate"] += 1

    manifest: dict[str, Any] = {"counts": dict(counts)}
    if apply:
        manifest["mode"] = "apply"
        if migrated_count == 0 and not counts:
            manifest["counts"] = {"skipped": 0, "migrated": 0}
    else:
        manifest["mode"] = "dry-run"
        if "would_migrate" not in manifest["counts"]:
            manifest["counts"] = {"would_migrate": 0}

    return manifest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate ADAD task snapshots from schema v2 to v3")
    parser.add_argument("tasks_dir", nargs="?", default=".agents/tasks")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive-dir", default=".agents/archive")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--migrated-at")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = migrate_tasks(
        args.tasks_dir,
        apply=args.apply,
        archive_dir=args.archive_dir,
        project_root=args.project_root,
        migrated_at=args.migrated_at,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
