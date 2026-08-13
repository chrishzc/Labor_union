"""Read-only dependency checks shared by operator-facing launchers."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROFILE_REQUIREMENTS = {
    "local-windows": {
        "commands": ("docker-compose",),
        "files": ("docker-compose.yml", "scripts/wait_for_db.py", "ui/app.py"),
        "modules": ("uvicorn", "streamlit", "scripts.run_line_worker", "scripts.run_service_monitor", "scripts.run_durable_job_worker"),
    },
    "local-unix": {
        "commands": ("docker", "lsof"),
        "files": ("docker-compose.yml", "scripts/wait_for_db.py", "ui/app.py"),
        "modules": ("uvicorn", "streamlit", "scripts.run_line_worker", "scripts.run_service_monitor", "scripts.run_durable_job_worker"),
    },
    "admin-no-auth": {"files": (), "modules": ()},
    "database-update": {
        "files": (".env", "db/schema.sql", "db/schema_parts"),
        "modules": ("scripts.update_local_database",),
    },
    "database-reset": {
        "files": (".env", "fixtures/db_snapshot_v2/v3/manifest.json"),
        "modules": ("scripts.reset_fake_database",),
    },
    "ngrok-development": {
        "commands": ("ngrok",),
        "files": (".env", "ui/app.py"),
        "modules": ("uvicorn", "streamlit", "scripts.run_line_worker", "scripts.run_service_monitor"),
    },
}


def _command_exists(command: str) -> bool:
    if command == "ngrok" and (PROJECT_ROOT / ".venv/Scripts/ngrok.exe").exists():
        return True
    return shutil.which(command) is not None


def inspect_profile(profile: str) -> dict[str, object]:
    requirements = PROFILE_REQUIREMENTS[profile]
    missing_commands = [name for name in requirements.get("commands", ()) if not _command_exists(name)]
    missing_files = [name for name in requirements.get("files", ()) if not (PROJECT_ROOT / name).exists()]
    missing_modules = [name for name in requirements.get("modules", ()) if importlib.util.find_spec(name) is None]
    issues = {
        "commands": missing_commands,
        "files": missing_files,
        "modules": missing_modules,
    }
    return {
        "status": "ready" if not any(issues.values()) else "blocked",
        "profile": profile,
        "project_root": str(PROJECT_ROOT),
        "missing": issues,
        "side_effects": "none",
    }


def run_profile(profile: str) -> int:
    report = inspect_profile(profile)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ready" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=tuple(PROFILE_REQUIREMENTS), required=True)
    return run_profile(parser.parse_args().profile)


if __name__ == "__main__":
    raise SystemExit(main())
