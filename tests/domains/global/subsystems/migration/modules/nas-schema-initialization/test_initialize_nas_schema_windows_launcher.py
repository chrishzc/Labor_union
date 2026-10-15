"""Exercise the actual Windows batch interaction with isolated child-process results."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[7]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows batch interaction")


@pytest.fixture
def launcher(tmp_path):
    project = tmp_path / "project with spaces"
    entry = project / "scripts/launchers/initialize_nas_schema.bat"
    entry.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/launchers/initialize_nas_schema.bat", entry)
    (project / ".venv/Scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / ".venv/Scripts/python.exe", project / ".venv/Scripts/python.exe")
    shutil.copyfile(ROOT / ".venv/pyvenv.cfg", project / ".venv/pyvenv.cfg")
    calls = project / "calls.jsonl"
    # The real batch and interpreter run; only the DB command's outcome is
    # controlled. Full schema/empty-target behavior has separate MySQL tests.
    (project / "scripts/initialize_nas_schema.py").write_text(
        'import json, os, sys\n'
        'with open(os.environ["NAS_LAUNCHER_CALLS"], "a", encoding="utf-8") as f:\n'
        '    f.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        'applying = "--apply" in sys.argv\n'
        'print("APPLY_RESULT" if applying else "PREFLIGHT_RESULT")\n'
        'sys.exit(int(os.environ["NAS_APPLY_EXIT" if applying else "NAS_PREFLIGHT_EXIT"]))\n',
        encoding="utf-8",
    )
    return entry, calls


@pytest.mark.parametrize("answer,preflight_exit,apply_exit,expected_calls,expected_exit", [
    ("Y\n\n", 0, 0, [[], ["--apply"]], 0),
    ("N\n\n", 0, 0, [[]], 0),
    ("Y\n\n", 0, 9, [[], ["--apply"]], 9),
    ("\n", 7, 0, [[]], 7),
    ("", 0, 0, [[]], 0),
])
def test_double_click_flow(launcher, answer, preflight_exit, apply_exit, expected_calls, expected_exit):
    entry, calls = launcher
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(entry)],
        input=answer, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, NAS_LAUNCHER_CALLS=str(calls),
                 NAS_PREFLIGHT_EXIT=str(preflight_exit), NAS_APPLY_EXIT=str(apply_exit)), timeout=20,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()] == expected_calls
    assert "pause" not in result.stderr.lower()
    if preflight_exit:
        assert "Press Y" not in result.stdout
    if expected_calls == [[], ["--apply"]] and not apply_exit:
        assert "[Done]" in result.stdout
    if expected_calls == [[]] and not preflight_exit:
        assert "[Cancelled]" in result.stdout


@pytest.mark.parametrize("argument", ["--dry-run", "--apply", "--help"])
def test_explicit_arguments_remain_noninteractive(launcher, argument):
    entry, calls = launcher
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(entry), argument],
        input="", capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, NAS_LAUNCHER_CALLS=str(calls), NAS_PREFLIGHT_EXIT="0", NAS_APPLY_EXIT="0"),
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()] == [[argument]]
    assert "Press Y" not in result.stdout
    assert "continue" not in result.stdout.lower()
