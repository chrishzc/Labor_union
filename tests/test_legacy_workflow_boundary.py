from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE_ROOTS = (
    "api",
    "domains",
    "infrastructure",
    "line",
    "scripts",
    "services",
    "subsystems",
    "ui",
)


def _runtime_python_sources() -> list[Path]:
    source_paths = []
    for source_root in RUNTIME_SOURCE_ROOTS:
        source_paths.extend((PROJECT_ROOT / source_root).rglob("*.py"))
    return source_paths


def test_retired_workflow_is_confined_to_ignored_history() -> None:
    legacy_name = "ad" + "ad"
    workflow_directory = PROJECT_ROOT / ".agents" / "skills" / f"{legacy_name}-workflow"

    assert not workflow_directory.exists()
    assert f"history/{legacy_name}/" in (PROJECT_ROOT / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert all(hook.suffix == ".sample" for hook in (PROJECT_ROOT / ".git" / "hooks").iterdir())
    assert all(
        legacy_name not in source_path.read_text(encoding="utf-8").lower()
        for source_path in _runtime_python_sources()
    )
