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
    # Run the real batch, interpreter and Python interaction. Only the DB
    # executor is substituted; MySQL tests cover the actual destructive writer.
    (project / "scripts/initialize_nas_schema.py").write_text(
        'import importlib.util, json, os, site, sys\n'
        f'site.addsitedir({str(ROOT / ".venv/Lib/site-packages")!r})\n'
        f'sys.path.insert(0, {str(ROOT)!r})\n'
        'import scripts\n'
        f'scripts.__path__.append({str(ROOT / "scripts")!r})\n'
        f'spec = importlib.util.spec_from_file_location("nas_real", {str(ROOT / "scripts/initialize_nas_schema.py")!r})\n'
        'nas = importlib.util.module_from_spec(spec)\n'
        'spec.loader.exec_module(nas)\n'
        'def record(value):\n'
        '    with open(os.environ["NAS_LAUNCHER_CALLS"], "a", encoding="utf-8") as f:\n'
        '        f.write(json.dumps(value) + "\\n")\n'
        'record(sys.argv[1:])\n'
        'def initialize(config, plan, *, apply=False, reset=False, confirm_reset=None):\n'
        '    if apply: record(["reset" if reset else "apply"])\n'
        '    code = int(os.environ["NAS_APPLY_EXIT" if apply else "NAS_PREFLIGHT_EXIT"])\n'
        '    if not apply and code == 2: raise nas._NonEmptyDatabase("Existing test database")\n'
        '    if code: raise nas.InitializationBlocked("synthetic failure")\n'
        '    target = {"host": "nas.test", "port": 3307, "database": "union_db", "server": "synthetic"}\n'
        '    if reset and not confirm_reset(target): return {"status": "cancelled"}\n'
        '    return {"status": "passed" if apply else "ready"}\n'
        'nas.initialize = initialize\n'
        'nas.load_configuration = lambda: {}\n'
        'nas.schema_plan = lambda: {"steps": [], "schema_parts": [], "assembly_id": "synthetic"}\n'
        'sys.exit(nas.main())\n',
        encoding="utf-8",
    )
    return entry, calls


@pytest.mark.parametrize("answer,preflight_exit,apply_exit,expected_calls,expected_exit", [
    ("Y\n\n", 0, 0, [["--interactive"], ["apply"]], 0),
    ("N\n\n", 0, 0, [["--interactive"]], 0),
    ("Y\n\n", 0, 9, [["--interactive"], ["apply"]], 1),
    ("\n", 7, 0, [["--interactive"]], 1),
    ("", 0, 0, [["--interactive"]], 0),
    ("R\nRESET union_db\n\n", 2, 0, [["--interactive"], ["reset"]], 0),
    ("R\nY\n\n", 2, 0, [["--interactive"], ["reset"]], 0),
    ("R\n", 2, 0, [["--interactive"], ["reset"]], 0),
    ("N\n\n", 2, 0, [["--interactive"]], 0),
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
    if preflight_exit not in (0, 2):
        assert "Press Y" not in result.stdout
        assert "Press R" not in result.stdout
    if answer.startswith("Y") and not preflight_exit and not apply_exit:
        assert "[Done]" in result.stdout
    if answer.startswith("N") or not answer or (preflight_exit == 2 and "RESET union_db" not in answer):
        assert "[Cancelled]" in result.stdout
    if preflight_exit == 2 and answer.startswith("R"):
        assert "nas.test:3307 / union_db" in result.stdout
        assert "ALL tables" in result.stdout
        assert ("[Done]" in result.stdout) == ("RESET union_db" in answer)


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
    expected = [[argument], ["apply"]] if argument == "--apply" else [[argument]]
    assert [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()] == expected
    assert "Press Y" not in result.stdout
    assert "continue" not in result.stdout.lower()
