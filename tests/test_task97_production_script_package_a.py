"""Focused checks for Task 97 production-script package A."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts import migrate_order_contract_identity as contract_identity
from scripts import migrate_order_details_lifecycle_version_view as lifecycle_view
from scripts import migrate_order_lifecycle_control_facts as control_facts
from scripts import migrate_scheduling_generation_bootstrap as scheduling_bootstrap


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_RUNNER = ROOT / "scripts/migrate_preserved_database_additive_schema.py"
CANONICAL_TARGETS = (
    "scripts/migrate_order_contract_identity.py",
    "scripts/migrate_order_details_lifecycle_version_view.py",
    "scripts/migrate_order_lifecycle_control_facts.py",
)
NON_CANONICAL_TARGET = "scripts/migrate_scheduling_generation_bootstrap.py"


def _has_main_guard(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(
            isinstance(comparator, ast.Constant)
            and comparator.value == "__main__"
            for comparator in node.test.comparators
        )
        for node in ast.walk(tree)
    )


def _has_top_level_symbol(tree: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
        for node in tree.body  # type: ignore[attr-defined]
    )


def test_canonical_runner_calls_first_three_package_a_scripts_via_subprocess() -> None:
    source = CANONICAL_RUNNER.read_text(encoding="utf-8")

    for target in CANONICAL_TARGETS:
        assert target in source
    assert "def run_candidate_post_schema(" in source
    assert "_run_project_python" in source
    assert "contract_apply = _run_project_python(" in source
    assert "view_dry = _run_project_python(" in source
    assert "dry = _run_project_python(" in source


def test_subprocess_called_scripts_keep_cli_identity_until_runner_is_rewritten() -> None:
    for relative_path in (*CANONICAL_TARGETS, NON_CANONICAL_TARGET):
        tree = ast.parse(
            (ROOT / relative_path).read_text(encoding="utf-8"),
            filename=relative_path,
        )
        assert _has_main_guard(tree), relative_path
        assert _has_top_level_symbol(tree, "main"), relative_path


def test_package_a_library_symbols_remain_importable() -> None:
    assert callable(contract_identity.migrate)
    assert callable(contract_identity.retire_legacy_contract_column)
    assert callable(lifecycle_view.run_migration)
    assert callable(lifecycle_view.canonical_view_statement)
    assert callable(control_facts.run_migration)
    assert callable(control_facts.validate_backup)


def test_scheduling_script_is_not_a_canonical_runner_caller() -> None:
    path = ROOT / NON_CANONICAL_TARGET
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=NON_CANONICAL_TARGET)

    assert _has_main_guard(tree)
    assert _has_top_level_symbol(tree, "main")
    assert NON_CANONICAL_TARGET not in CANONICAL_RUNNER.read_text(encoding="utf-8")
