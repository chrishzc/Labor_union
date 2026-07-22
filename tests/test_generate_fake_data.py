import ast
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "scripts" / "generate_fake_data.py"
FROZEN_ERROR = (
    "GenerateFakeData 已凍結，僅供人工參考；"
    "新增假資料需求請建立獨立腳本與 ADAD 節點。"
)


def _assert_frozen_guard():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    assert ast.get_docstring(module)
    assert isinstance(module.body[1], ast.Raise)
    assert isinstance(module.body[1].exc, ast.Call)
    assert isinstance(module.body[1].exc.func, ast.Name)
    assert module.body[1].exc.func.id == "SystemExit"
    assert ast.literal_eval(module.body[1].exc.args[0]) == FROZEN_ERROR

    first_import_index = next(
        index
        for index, statement in enumerate(module.body)
        if isinstance(statement, (ast.Import, ast.ImportFrom))
    )
    assert first_import_index > 1


def _run_python(*args):
    _assert_frozen_guard()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_frozen_guard_is_the_first_executable_statement():
    _assert_frozen_guard()


def test_direct_execution_fails_before_legacy_generation():
    result = _run_python(str(SOURCE_PATH))

    assert result.returncode != 0
    assert FROZEN_ERROR in result.stderr
    assert "正在初始化生成假資料程序" not in result.stdout
    assert "所有假資料生成完成" not in result.stdout


def test_legacy_flags_cannot_reenable_generation():
    result = _run_python(
        str(SOURCE_PATH),
        "--seed-db",
        "--replace-demo-db",
        "--seed",
        "20260722",
        "--reference-date",
        "2026-07-22",
    )

    assert result.returncode != 0
    assert FROZEN_ERROR in result.stderr
    assert "正在初始化生成假資料程序" not in result.stdout


def test_import_is_rejected_before_runtime_dependencies_load():
    result = _run_python(
        "-c",
        (
            "import sys\n"
            "try:\n"
            "    import scripts.generate_fake_data\n"
            "except SystemExit as exc:\n"
            "    print(str(exc), file=sys.stderr)\n"
            "    print('pandas_loaded=' + str('pandas' in sys.modules), file=sys.stderr)\n"
            "    print('db_service_loaded=' + str('services.db_service' in sys.modules), file=sys.stderr)\n"
            "    raise\n"
        ),
    )

    assert result.returncode != 0
    assert FROZEN_ERROR in result.stderr
    assert "pandas_loaded=False" in result.stderr
    assert "db_service_loaded=False" in result.stderr


def test_historical_implementation_remains_reference_only():
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "def parse_cli_args():" in source
    assert "def main():" in source
    assert "generate_roster_data(" in source
    assert "generate_finance_data(" in source
    assert 'if __name__ == "__main__":' in source
