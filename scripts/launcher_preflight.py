"""
File: launcher_preflight.py
Description: 唯讀檢查 FastAPI＋React launcher 依賴、React artifact 與 12-entry runtime state 邊界。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil

from dotenv import dotenv_values

from subsystems.line.runtime_cutover import (
    LineRuntimeCutoverError,
    validate_line_worker_runtime,
)
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminArtifactError,
    load_react_admin_runtime_from_environment,
)
from scripts.provision_admin_entry_target_state import attest_state
from subsystems.access.admin_entry_target_control import EntryTargetError


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROFILE_REQUIREMENTS = {
    "artifact-runtime": {
        "files": ("api/main.py", "infrastructure/runtime/react_admin_artifact.py"),
        "modules": ("uvicorn",),
    },
    "dual-run": {
        "commands": ("npm",),
        "files": (
            "ui_react/package.json",
            "ui_react/src/main.tsx",
            "ui_react/index.html",
        ),
        "modules": ("uvicorn",),
    },
    "local-windows": {
        "commands": ("docker-compose", "npm"),
        "files": ("docker-compose.yml", "scripts/wait_for_db.py", "ui_react/package.json", "ui_react/src/main.tsx", "ui_react/index.html"),
        "modules": ("uvicorn", "scripts.run_line_worker", "scripts.run_service_monitor", "scripts.run_durable_job_worker", "scripts.smoke_local_development_launcher"),
    },
    "local-unix": {
        "commands": ("docker", "npm"),
        "files": ("docker-compose.yml", "scripts/wait_for_db.py", "ui_react/package.json", "ui_react/src/main.tsx", "ui_react/index.html"),
        "modules": ("uvicorn", "scripts.run_line_worker", "scripts.run_service_monitor", "scripts.run_durable_job_worker"),
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
    "line-worker": {"files": (".env",), "modules": ("scripts.run_line_worker",)},
}


def _command_exists(command: str) -> bool:
    if command == "ngrok" and (PROJECT_ROOT / ".venv/Scripts/ngrok.exe").exists():
        return True
    return shutil.which(command) is not None


def _configuration_issues(profile: str) -> list[str]:
    if profile != "line-worker":
        return []
    environment = {
        key: value or "" for key, value in dotenv_values(PROJECT_ROOT / ".env").items()
    }
    try:
        validate_line_worker_runtime(environment)
    except LineRuntimeCutoverError:
        return ["LINE worker credentials or runtime selection"]
    return []


def inspect_profile(profile: str) -> dict[str, object]:
    requirements = PROFILE_REQUIREMENTS[profile]
    missing_commands = [name for name in requirements.get("commands", ()) if not _command_exists(name)]
    missing_files = [name for name in requirements.get("files", ()) if not (PROJECT_ROOT / name).exists()]
    missing_modules = [name for name in requirements.get("modules", ()) if importlib.util.find_spec(name) is None]
    issues = {
        "commands": missing_commands,
        "files": missing_files,
        "modules": missing_modules,
        "configuration": _configuration_issues(profile),
    }
    report = {
        "status": "ready" if not any(issues.values()) else "blocked",
        "profile": profile,
        "project_root": str(PROJECT_ROOT),
        "missing": issues,
        "side_effects": "none",
    }
    if profile == "artifact-runtime":
        try:
            state_path = os.environ.get("ADMIN_ENTRY_TARGET_STATE_PATH", "").strip()
            if not state_path:
                raise EntryTargetError(
                    "unavailable",
                    "entry_target_state_path_missing",
                    "Entry target runtime state path 未設定",
                )
            report["entry_target_attestation"] = attest_state(Path(state_path))
            runtime = load_react_admin_runtime_from_environment(workspace_root=PROJECT_ROOT)
            if runtime is None:
                raise ReactAdminArtifactError("react admin artifact runtime is not configured")
            report["artifact_attestation"] = runtime.health_attestation()
            report["streamlit_rollback"] = {
                "status": "retained",
                "health_url": "http://127.0.0.1:8501/_stcore/health",
            }
            report["ports"] = [8000, 8501]
            report["startup_order"] = [
                "entry-target-preflight",
                "artifact-preflight",
                "api",
                "artifact-private-health",
                "streamlit",
            ]
        except EntryTargetError:
            issues["configuration"].append("Admin entry target runtime state attestation")
            report["status"] = "blocked"
        except (OSError, ReactAdminArtifactError, ValueError):
            issues["configuration"].append("React admin current/previous selector attestation")
            report["status"] = "blocked"
    if profile == "dual-run":
        report["planned_commands"] = [
            "python -m uvicorn api.main:app --host 127.0.0.1 --port 8000",
            "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        ]
        report["ports"] = [8000, 5173]
        report["health_predicates"] = {
            "api": "GET /health == 200",
            "react": "GET /admin/ == 200, HTML, body contains id=\"root\"",
            "proxy": "GET /api/... through 5173; browser uses relative /api",
        }
        report["startup_order"] = ["api", "react"]
        report["disabled"] = [
            "streamlit",
            "monitor",
            "LINE delivery",
            "durable worker",
            "incident worker",
            "knowledge worker",
            "consumer/provider workers",
        ]
    return report


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
