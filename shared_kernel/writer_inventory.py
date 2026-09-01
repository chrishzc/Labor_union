"""Deterministic production SQL-writer inventory and baseline validation."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
import re
from typing import Any

_WRITER_METHODS = frozenset({"execute", "executemany", "commit"})
_MUTATING_SQL_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)
_TABLE_PATTERN = re.compile(
    r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO|"
    r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE)"
    r"\s+`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
_INVENTORY_CONTRACT = "production-writer-inventory/v1"


@dataclass(frozen=True, slots=True)
class WriterFinding:
    relative_path: str
    symbol: str
    method: str
    operation: str
    table: str
    fingerprint: str
    occurrence: int = 1

    @property
    def identity(self) -> str:
        return ":".join(
            (
                self.relative_path,
                self.symbol,
                self.method,
                self.operation,
                self.table,
                self.fingerprint,
                str(self.occurrence),
            )
        )


@dataclass(frozen=True, slots=True)
class WriterOwnerRule:
    patterns: tuple[str, ...]
    owner: str
    runtime_class: str
    legacy_status: str
    exit_slice: str
    strategy: str


@dataclass(frozen=True, slots=True)
class GoneRouteRule:
    relative_path: str
    symbols: tuple[str, ...]
    forbidden_calls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WriterInventoryBaseline:
    roots: tuple[str, ...]
    no_sql_zones: tuple[str, ...]
    finding_count: int
    scan_fingerprint: str
    owner_rules: tuple[WriterOwnerRule, ...]
    gone_route_rules: tuple[GoneRouteRule, ...]


class WriterInventoryDrift(RuntimeError):
    """Raised when production writer evidence differs from its baseline."""


def scan_production_writers(
    repository_root: Path,
    roots: tuple[str, ...],
) -> tuple[WriterFinding, ...]:
    findings: list[WriterFinding] = []
    for root_name in roots:
        root_path = repository_root / root_name
        for source_path in sorted(root_path.rglob("*.py")):
            findings.extend(_scan_source_file(repository_root, source_path))
    return tuple(sorted(findings, key=lambda finding: finding.identity))


def validate_writer_inventory(
    repository_root: Path,
    baseline_path: Path,
) -> tuple[WriterFinding, ...]:
    baseline = load_writer_inventory_baseline(baseline_path)
    _validate_no_sql_zones(repository_root, baseline.no_sql_zones)
    findings = scan_production_writers(repository_root, baseline.roots)
    _validate_owner_coverage(findings, baseline.owner_rules)
    _validate_gone_routes(repository_root, baseline.gone_route_rules)
    if len(findings) != baseline.finding_count:
        raise WriterInventoryDrift("production writer count changed")
    if writer_scan_fingerprint(findings) != baseline.scan_fingerprint:
        raise WriterInventoryDrift("production writer fingerprint changed")
    return findings


def writer_scan_fingerprint(findings: tuple[WriterFinding, ...]) -> str:
    payload = "\n".join(finding.identity for finding in findings).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_writer_inventory_baseline(path: Path) -> WriterInventoryBaseline:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != _INVENTORY_CONTRACT:
        raise ValueError("unsupported writer inventory contract")
    rules = tuple(_build_owner_rule(item) for item in payload["owner_rules"])
    gone_routes = tuple(
        _build_gone_route_rule(item)
        for item in payload.get("gone_route_rules", ())
    )
    return WriterInventoryBaseline(
        roots=tuple(payload["roots"]),
        no_sql_zones=tuple(payload["no_sql_zones"]),
        finding_count=int(payload["finding_count"]),
        scan_fingerprint=str(payload["scan_fingerprint"]),
        owner_rules=rules,
        gone_route_rules=gone_routes,
    )


def _scan_source_file(
    repository_root: Path,
    source_path: Path,
) -> list[WriterFinding]:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    relative_path = source_path.relative_to(repository_root).as_posix()
    visitor = _WriterCallVisitor(
        relative_path,
        _module_string_constants(tree),
    )
    visitor.visit(tree)
    return visitor.findings


class _WriterCallVisitor(ast.NodeVisitor):
    def __init__(
        self,
        relative_path: str,
        string_constants: dict[str, str],
    ) -> None:
        self.relative_path = relative_path
        self.string_constants = string_constants
        self.symbol_stack: list[str] = []
        self.findings: list[WriterFinding] = []
        self.occurrences: dict[tuple[str, str, str, str, str], int] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_symbol(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_symbol(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_symbol(node)

    def visit_Call(self, node: ast.Call) -> None:
        method = _call_method_name(node)
        if method not in _WRITER_METHODS:
            self.generic_visit(node)
            return
        finding = _build_finding(
            self.relative_path,
            self._symbol(),
            method,
            node,
            self.string_constants,
        )
        if finding is not None:
            key = (
                finding.symbol,
                finding.method,
                finding.operation,
                finding.table,
                finding.fingerprint,
            )
            occurrence = self.occurrences.get(key, 0) + 1
            self.occurrences[key] = occurrence
            finding = replace(finding, occurrence=occurrence)
            self.findings.append(finding)
        self.generic_visit(node)

    def _visit_symbol(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def _symbol(self) -> str:
        return ".".join(self.symbol_stack) or "<module>"


def _build_finding(
    relative_path: str,
    symbol: str,
    method: str,
    call: ast.Call,
    string_constants: dict[str, str],
) -> WriterFinding | None:
    sql = _constant_sql(call, string_constants)
    if method != "commit" and sql is not None and not _MUTATING_SQL_PATTERN.match(sql):
        return None
    operation, table = _classify_writer(method, sql)
    return WriterFinding(
        relative_path,
        symbol,
        method,
        operation,
        table,
        _call_fingerprint(call),
    )


def _call_fingerprint(call: ast.Call) -> str:
    return writer_call_fingerprint(call)


def writer_call_fingerprint(call: ast.Call) -> str:
    normalized_call = _stable_ast_dump(call).encode("utf-8")
    return hashlib.sha256(normalized_call).hexdigest()[:16]


def _stable_ast_dump(value: Any) -> str:
    if isinstance(value, ast.AST):
        fields = [
            f"{name}={_stable_ast_dump(field_value)}"
            for name, field_value in ast.iter_fields(value)
            if field_value is not None and field_value != []
        ]
        return f"{type(value).__name__}({', '.join(fields)})"
    if isinstance(value, list):
        return f"[{', '.join(_stable_ast_dump(item) for item in value)}]"
    return repr(value)


def _constant_sql(
    call: ast.Call,
    string_constants: dict[str, str],
) -> str | None:
    if not call.args:
        return None
    return _string_expression(call.args[0], string_constants)


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    unresolved = list(tree.body)
    for _ in range(len(unresolved) + 1):
        remaining = []
        for node in unresolved:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            target, value = _assignment_parts(node)
            resolved = _string_expression(value, constants)
            if target is None or resolved is None:
                remaining.append(node)
                continue
            constants[target] = resolved
        if len(remaining) == len(unresolved):
            break
        unresolved = remaining
    return constants


def _assignment_parts(node):
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None, node.value
        return node.targets[0].id, node.value
    if not isinstance(node.target, ast.Name):
        return None, node.value
    return node.target.id, node.value


def _string_expression(node, constants) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_expression(node.left, constants)
        right = _string_expression(node.right, constants)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        return _joined_string(node, constants)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    ):
        return _string_expression(node.func.value, constants)
    return None


def _joined_string(node, constants) -> str | None:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.FormattedValue):
            parts.append("{dynamic}")
            continue
        resolved = _string_expression(value, constants)
        if resolved is None:
            return None
        parts.append(resolved)
    return "".join(parts)


def _classify_writer(method: str, sql: str | None) -> tuple[str, str]:
    if method == "commit":
        return "COMMIT", "-"
    if sql is None:
        return "DYNAMIC", "unknown"
    operation_match = _MUTATING_SQL_PATTERN.match(sql)
    operation = operation_match.group(1).upper() if operation_match else "DYNAMIC"
    table_match = _TABLE_PATTERN.match(sql)
    return operation, table_match.group(1) if table_match else "unknown"


def _call_method_name(call: ast.Call) -> str:
    if not isinstance(call.func, ast.Attribute):
        return ""
    return call.func.attr


def _build_owner_rule(payload: Any) -> WriterOwnerRule:
    if not isinstance(payload, dict):
        raise TypeError("writer owner rule must be an object")
    return WriterOwnerRule(
        patterns=tuple(payload["patterns"]),
        owner=payload["owner"],
        runtime_class=payload["runtime_class"],
        legacy_status=payload["legacy_status"],
        exit_slice=payload["exit_slice"],
        strategy=payload["strategy"],
    )


def _build_gone_route_rule(payload: Any) -> GoneRouteRule:
    if not isinstance(payload, dict):
        raise TypeError("gone route rule must be an object")
    return GoneRouteRule(
        relative_path=str(payload["relative_path"]),
        symbols=tuple(payload["symbols"]),
        forbidden_calls=tuple(payload["forbidden_calls"]),
    )


def _validate_owner_coverage(
    findings: tuple[WriterFinding, ...],
    rules: tuple[WriterOwnerRule, ...],
) -> None:
    for finding in findings:
        matching_rules = [
            rule
            for rule in rules
            if any(fnmatch(finding.relative_path, pattern) for pattern in rule.patterns)
        ]
        if len(matching_rules) != 1:
            raise WriterInventoryDrift(
                f"writer owner coverage must be unique: {finding.relative_path}"
            )


def _validate_gone_routes(
    repository_root: Path,
    rules: tuple[GoneRouteRule, ...],
) -> None:
    for rule in rules:
        source_path = repository_root / rule.relative_path
        functions = _module_functions(source_path)
        for symbol in rule.symbols:
            route = functions.get(symbol)
            if route is None:
                raise WriterInventoryDrift(
                    f"configured Gone route is missing: {rule.relative_path}:{symbol}"
                )
            _validate_gone_route_calls(rule, symbol, route, functions)


def _module_functions(source_path: Path) -> dict[str, ast.FunctionDef]:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _validate_gone_route_calls(rule, symbol, route, functions) -> None:
    calls = _reachable_function_calls(route, functions, frozenset())
    forbidden = tuple(
        call
        for call in calls
        if _gone_route_call_is_forbidden(call, rule.forbidden_calls)
    )
    if forbidden:
        call_list = ",".join(sorted(forbidden))
        raise WriterInventoryDrift(
            f"Gone route calls retired writer: "
            f"{rule.relative_path}:{symbol}:{call_list}"
        )


def _reachable_function_calls(node, functions, visited):
    if node.name in visited:
        return frozenset()
    next_visited = visited | {node.name}
    direct_calls = frozenset(_body_call_references(node))
    nested_calls = (
        _reachable_function_calls(functions[call], functions, next_visited)
        for call in direct_calls
        if call in functions
    )
    return direct_calls.union(*(nested_calls))


def _body_call_references(node) -> tuple[str, ...]:
    return tuple(
        reference
        for statement in node.body
        for candidate in ast.walk(statement)
        if isinstance(candidate, ast.Call)
        if (reference := _call_reference(candidate))
    )


def _call_reference(call: ast.Call) -> str:
    parts: list[str] = []
    current = call.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _gone_route_call_is_forbidden(
    call_reference: str,
    forbidden_patterns: tuple[str, ...],
) -> bool:
    method = call_reference.rsplit(".", 1)[-1]
    if method in _WRITER_METHODS:
        return True
    return any(fnmatch(call_reference, pattern) for pattern in forbidden_patterns)


def _validate_no_sql_zones(
    repository_root: Path,
    zones: tuple[str, ...],
) -> None:
    findings = scan_production_writers(repository_root, zones)
    if findings:
        raise WriterInventoryDrift("concrete SQL writer found in no-SQL zone")
