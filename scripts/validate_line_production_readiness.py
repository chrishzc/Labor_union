"""Validate Stage 10 LINE production configuration without exposing secret values."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from shared_kernel.migration_release import load_migration_release_manifest

from subsystems.line.runtime_cutover import (
    LineRuntimeCutoverError,
    load_line_cutover_release,
    production_readiness_report,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        report = production_readiness_report(os.environ)
        _require_production_environment(report)
        release = _load_release()
        _validate_migration_manifests(release.migration_manifests)
    except (LineRuntimeCutoverError, OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, ensure_ascii=False))
        return 2
    report["release_id"] = release.release_id
    report["restart_targets"] = release.required_restart_targets
    report["smoke_ids"] = release.post_cutover_smoke_ids
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _load_release():
    path = PROJECT_ROOT / "db" / "cutover_releases" / (
        "labor_union_2026_08_09_line_stage10_v1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return load_line_cutover_release(payload)


def _validate_migration_manifests(names: tuple[str, ...]) -> None:
    release_root = PROJECT_ROOT / "db" / "migration_releases"
    for name in names:
        load_migration_release_manifest(release_root / name, PROJECT_ROOT)


def _require_production_environment(report: dict[str, object]) -> None:
    if report["app_environment"] not in {"prod", "production"}:
        raise LineRuntimeCutoverError(
            "online startup requires APP_ENV=production"
        )


if __name__ == "__main__":
    raise SystemExit(main())
