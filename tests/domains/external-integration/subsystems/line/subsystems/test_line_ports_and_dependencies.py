"""Architecture tests for LINE typed ports and pure Domain dependencies."""

import ast
from pathlib import Path

from shared_kernel.ports import UnitOfWork
from subsystems.line.ports import LineUnitOfWorkPort

PROJECT_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)
LINE_DOMAIN_DIRECTORY = PROJECT_ROOT / "domains" / "line"
LINE_SUBSYSTEM_DIRECTORY = PROJECT_ROOT / "subsystems" / "line"
FORBIDDEN_IMPORT_PREFIXES = (
    "api",
    "fastapi",
    "infrastructure",
    "linebot",
    "pymysql",
    "requests",
    "streamlit",
    "chromadb",
)


def test_line_unit_of_work_extends_global_unit_of_work_contract() -> None:
    assert UnitOfWork in LineUnitOfWorkPort.__mro__
    assert LineUnitOfWorkPort._is_protocol is True


def test_line_domain_has_no_framework_or_infrastructure_imports() -> None:
    violations: list[str] = []
    for path in sorted(LINE_DOMAIN_DIRECTORY.glob("*.py")):
        violations.extend(_forbidden_imports(path))

    assert violations == []


def test_line_contracts_have_no_concrete_adapter_imports() -> None:
    contract_paths = sorted(LINE_SUBSYSTEM_DIRECTORY.glob("*_contracts.py"))
    contract_paths.extend(
        [
            LINE_SUBSYSTEM_DIRECTORY / "capabilities.py",
            LINE_SUBSYSTEM_DIRECTORY / "ports.py",
        ]
    )
    violations = [
        violation
        for path in contract_paths
        for violation in _forbidden_imports(path)
    ]

    assert violations == []


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = _imported_modules(tree)
    return [
        f"{path.name}:{module}"
        for module in imports
        if module.startswith(FORBIDDEN_IMPORT_PREFIXES)
    ]


def _imported_modules(tree: ast.AST) -> tuple[str, ...]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)
