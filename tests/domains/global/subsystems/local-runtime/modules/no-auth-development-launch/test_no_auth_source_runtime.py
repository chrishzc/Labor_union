from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).parents[7]
SOURCE = (
    ROOT / "scripts" / "launchers" / "start_local_development_no_auth.sh"
).read_text(encoding="utf-8")


def test_no_auth_launcher_forces_source_runtime_before_delegation() -> None:
    delegate = 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"'

    for statement in (
        "export REACT_ADMIN_RUNTIME_PROFILE=source",
        "export REACT_ADMIN_CURRENT_ARTIFACT_DIR=",
        "export REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=",
        "export REACT_ADMIN_ACTIVE_SELECTOR=",
    ):
        assert statement in SOURCE
        assert SOURCE.index(statement) < SOURCE.index(delegate)


def test_no_auth_launcher_injects_ephemeral_anomaly_key_without_persisting_or_overriding(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_python = project_root / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    project_python.chmod(0o755)

    delegate = 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"'
    stub = (
        'if [[ -n "$EXPECTED_ANOMALY_ISSUE_IDENTITY_KEY_V1" ]]; then '
        '[[ "$ANOMALY_ISSUE_IDENTITY_KEY_V1" == "$EXPECTED_ANOMALY_ISSUE_IDENTITY_KEY_V1" ]] '
        '&& printf "preserved=yes\\n" || printf "preserved=no\\n"; '
        'else printf "generated_length=%s\\n" "${#ANOMALY_ISSUE_IDENTITY_KEY_V1}"; fi'
    )
    source = (
        SOURCE.replace(
            'SCRIPT_DIR="${BASH_SOURCE[0]%/*}"',
            f'SCRIPT_DIR="{ROOT / "scripts" / "launchers"}"',
        )
        .replace(
            'PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"',
            f'PROJECT_ROOT="{project_root}"',
        )
        .replace(delegate, stub)
    )
    env = os.environ.copy()
    env.pop("ANOMALY_ISSUE_IDENTITY_KEY_V1", None)
    env["EXPECTED_ANOMALY_ISSUE_IDENTITY_KEY_V1"] = ""
    env["REACT_ADMIN_ACTIVE_SELECTOR"] = ""
    env["REACT_ADMIN_CURRENT_ARTIFACT_DIR"] = ""
    env["REACT_ADMIN_PREVIOUS_ARTIFACT_DIR"] = ""
    env["APP_ENV"] = "development"
    before = (ROOT / ".env").read_bytes() if (ROOT / ".env").exists() else None
    generated = subprocess.run(
        ["bash", "-c", source],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert generated.returncode == 0, generated.stderr
    assert generated.stdout.startswith("generated_length=")
    assert int(generated.stdout.split("=", 1)[1]) >= 32
    assert "ANOMALY_ISSUE_IDENTITY_KEY_V1=" not in generated.stdout
    after = (ROOT / ".env").read_bytes() if (ROOT / ".env").exists() else None
    assert after == before

    explicit = "provided-local-anomaly-key-that-is-at-least-32-bytes"
    env["ANOMALY_ISSUE_IDENTITY_KEY_V1"] = explicit
    env["EXPECTED_ANOMALY_ISSUE_IDENTITY_KEY_V1"] = explicit
    preserved = subprocess.run(
        ["bash", "-c", source],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert preserved.returncode == 0, preserved.stderr
    assert preserved.stdout == "preserved=yes\n"
