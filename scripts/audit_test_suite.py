from __future__ import annotations

import argparse
import ast
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEST_PATTERNS = ("test_*.py", "*_test.py")
INTEGRATION_NAME_HINTS = (
    "mysql",
    "disposable",
    "_e2e",
    "/e2e/",
    "/integration/",
)


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str


def iter_test_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in TEST_PATTERNS:
        files.update(root.rglob(pattern))
    return sorted(path for path in files if path.is_file())


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def is_pytest_skip_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "skip"
        and isinstance(func.value, ast.Name)
        and func.value.id == "pytest"
    )


def is_unconditional_skip_decorator(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "skip"
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "pytest"
    )


def is_trivial_assert(node: ast.AST) -> bool:
    if not isinstance(node, ast.Assert):
        return False
    test = node.test
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        left = test.left
        right = test.comparators[0]
        if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
            try:
                expression = ast.Expression(body=test)
                return bool(eval(compile(expression, "<audit>", "eval"), {"__builtins__": {}}, {}))
            except Exception:
                return False
    return False


def collect_test_defs(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            found.append(node)
    return found


def scope_duplicate_names(tree: ast.Module, path: Path) -> list[Finding]:
    findings: list[Finding] = []

    def inspect_scope(body: Iterable[ast.stmt], scope_name: str) -> None:
        seen: dict[str, int] = {}
        for item in body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                if item.name in seen:
                    findings.append(
                        Finding(
                            path,
                            f"shadowed test name {item.name!r} in {scope_name}; later definition replaces line {seen[item.name]}",
                        )
                    )
                else:
                    seen[item.name] = item.lineno

    inspect_scope(tree.body, "module scope")
    for item in tree.body:
        if isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            inspect_scope(item.body, f"class {item.name}")
    return findings


def source_has_integration_marker(source: str) -> bool:
    compact = source.replace(" ", "")
    return "pytest.mark.integration" in compact or "pytestmark=pytest.mark.integration" in compact


def audit(root: Path) -> tuple[list[Finding], list[Finding], dict[str, int]]:
    objective: list[Finding] = []
    review: list[Finding] = []
    files = iter_test_files(root)
    hashes: dict[str, list[Path]] = defaultdict(list)

    stats = {
        "files": len(files),
        "test_functions": 0,
        "integration_marked_files": 0,
        "unconditional_skip_tests": 0,
        "integration_marker_candidates": 0,
    }

    for path in files:
        source = path.read_text(encoding="utf-8")
        hashes[hashlib.sha256(source.encode("utf-8")).hexdigest()].append(path)

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            objective.append(Finding(path, f"syntax error: {exc.msg} at line {exc.lineno}"))
            continue

        tests = collect_test_defs(tree)
        stats["test_functions"] += len(tests)
        if not tests:
            objective.append(
                Finding(
                    path,
                    "matches pytest filename convention but defines no test_* function/method; rename or remove it",
                )
            )

        objective.extend(scope_duplicate_names(tree, path))

        for test in tests:
            body = strip_docstring(test.body)
            if not body:
                objective.append(Finding(path, f"{test.name} has an empty body"))
                continue
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                objective.append(Finding(path, f"{test.name} is pass-only"))
            if len(body) == 1 and is_trivial_assert(body[0]):
                objective.append(Finding(path, f"{test.name} contains only a trivially-true assertion"))
            if len(body) == 1 and isinstance(body[0], ast.Expr) and is_pytest_skip_call(body[0].value):
                review.append(Finding(path, f"{test.name} only calls pytest.skip()"))
                stats["unconditional_skip_tests"] += 1
            if any(is_unconditional_skip_decorator(dec) for dec in test.decorator_list):
                review.append(Finding(path, f"{test.name} is unconditionally @pytest.mark.skip"))
                stats["unconditional_skip_tests"] += 1

        integration_marked = source_has_integration_marker(source)
        if integration_marked:
            stats["integration_marked_files"] += 1
        normalized = "/" + path.as_posix().lower()
        if any(hint in normalized for hint in INTEGRATION_NAME_HINTS) and not integration_marked:
            review.append(
                Finding(
                    path,
                    "looks integration/E2E-oriented by path/name but has no pytest.mark.integration; confirm it is deterministic or classify it",
                )
            )
            stats["integration_marker_candidates"] += 1

    for duplicate_paths in hashes.values():
        if len(duplicate_paths) <= 1:
            continue
        joined = ", ".join(str(path) for path in duplicate_paths)
        for path in duplicate_paths:
            objective.append(Finding(path, f"exact duplicate test file content: {joined}"))

    return objective, review, stats


def print_findings(title: str, findings: list[Finding]) -> None:
    print(f"\n{title}: {len(findings)}")
    for finding in findings:
        print(f"- {finding.path}: {finding.message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit pytest files for objective dead/duplicate tests and review-worthy classification smells."
    )
    parser.add_argument("--tests-root", default="tests", type=Path)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Always exit zero; useful while reviewing existing test debt.",
    )
    args = parser.parse_args()

    objective, review, stats = audit(args.tests_root)
    print("Test-suite inventory")
    for key, value in stats.items():
        print(f"- {key}: {value}")
    print_findings("Objective problems (remove/fix before treating as CI protection)", objective)
    print_findings("Review candidates (semantic decision required)", review)

    if objective and not args.report_only:
        print("\nAudit failed: objective dead/duplicate test problems exist.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
