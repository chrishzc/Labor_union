"""Fail closed when a non-entry production module has no static caller."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    "api",
    "domains",
    "subsystems",
    "infrastructure",
    "line",
    "ui",
    "services",
    "scripts",
)
ENTRY_MODULES = frozenset({"api.main", "ui.app", "line.setup_rich_menus"})
ENTRY_PREFIXES = ("api.routes.", "ui.pages.", "scripts.")
APPROVED_UNCALLED_LEGACY_MODULES = frozenset()


def test_every_non_entry_production_module_has_a_static_caller() -> None:
    module_paths = _production_module_paths()
    callers = _static_callers(module_paths)

    orphaned = sorted(
        path.relative_to(ROOT).as_posix()
        for path, module in module_paths.items()
        if _requires_static_caller(path, module) and not callers[module]
    )

    assert orphaned == []


def test_every_api_route_module_is_mounted_by_the_application() -> None:
    route_modules = {
        path.stem
        for path in (ROOT / "api/routes").glob("*.py")
        if path.stem != "__init__"
    }

    assert route_modules - _mounted_router_modules() == set()


def test_nested_router_mount_requires_a_reachable_parent(tmp_path: Path) -> None:
    routes = tmp_path / "api/routes"
    routes.mkdir(parents=True)
    (tmp_path / "api/main.py").write_text(
        "from api.routes import parent\napp.include_router(parent.router)\n"
    )
    (routes / "parent.py").write_text(
        "from api.routes.child import router as child_router\n"
        "router.include_router(child_router)\n"
    )
    (routes / "child.py").write_text("")
    (routes / "orphan.py").write_text(
        "from api.routes.unmounted import router as unmounted_router\n"
        "router.include_router(unmounted_router)\n"
    )
    (routes / "unmounted.py").write_text("")
    (tmp_path / "api/nas_apps.py").write_text(
        "from api.routes.nas_setup import attach_setup\n"
        "from api.routes.nas_public import public_router as line_router\n"
        "def factory():\n"
        "    for item in (line_router,):\n"
        "        app.include_router(item)\n"
        "    return attach_setup(app)\n"
    )
    (routes / "nas_public.py").write_text("")
    (routes / "nas_setup.py").write_text(
        "def attach_setup(app):\n    app.include_router(router)\n    return app\n"
    )

    assert _mounted_router_modules(tmp_path) == {"parent", "child", "nas_public", "nas_setup"}


def _production_module_paths() -> dict[Path, str]:
    paths = [path for folder in SOURCE_ROOTS for path in (ROOT / folder).rglob("*.py")]
    return {path: _module_name(path) for path in paths}


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _static_callers(module_paths: dict[Path, str]) -> dict[str, set[str]]:
    callers: dict[str, set[str]] = defaultdict(set)
    known_modules = set(module_paths.values())
    for path, module in module_paths.items():
        _record_imports(path, _package_name(path, module), known_modules, callers)
    for path in (ROOT / "tests").rglob("*.py"):
        _record_imports(path, "", known_modules, callers)
    return callers


def _package_name(path: Path, module: str) -> str:
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _record_imports(path: Path, package: str, known_modules: set[str], callers: dict[str, set[str]]) -> None:
    for token in _import_tokens(path, package):
        for module in known_modules:
            if token == module or token.startswith(f"{module}."):
                callers[module].add(path.relative_to(ROOT).as_posix())


def _import_tokens(path: Path, package: str) -> tuple[str, ...]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    tokens: list[str] = []
    for node in ast.walk(tree):
        tokens.extend(_tokens_from_node(node, package))
    return tuple(tokens)


def _tokens_from_node(node: ast.AST, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return ()
    base = _resolved_import_base(node, package)
    if not base:
        return ()
    return (base, *(f"{base}.{alias.name}" for alias in node.names if alias.name != "*"))


def _resolved_import_base(node: ast.ImportFrom, package: str) -> str:
    base = node.module or ""
    if not node.level:
        return base
    segments = package.split(".") if package else []
    parent = segments[: max(0, len(segments) - node.level + 1)]
    return ".".join(part for part in (*parent, base) if part)


def _requires_static_caller(path: Path, module: str) -> bool:
    if path.name == "__init__.py" or module in ENTRY_MODULES:
        return False
    if module in APPROVED_UNCALLED_LEGACY_MODULES:
        return False
    return not module.startswith(ENTRY_PREFIXES)


def _mounted_router_modules(root: Path = ROOT) -> set[str]:
    pending = [path for path in (root / "api/main.py", root / "api/nas_apps.py") if path.exists()]
    visited: set[Path] = set()
    mounted: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: dict[str, str] = {}
        attachments: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if node.module == "api.routes":
                    imports[alias.asname or alias.name] = alias.name
                elif (node.module or "").startswith("api.routes."):
                    module = node.module.removeprefix("api.routes.")
                    if alias.name == "router" or alias.name.endswith("_router"):
                        imports[alias.asname or alias.name] = module
                    elif alias.name.startswith("attach_"):
                        attachments[alias.asname or alias.name] = module
        arguments: list[ast.AST] = []
        for call in ast.walk(tree):
            if _is_router_mount(call):
                arguments.append(call.args[0])
            elif isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                module = attachments.get(call.func.id)
                if module is not None:
                    mounted.add(module)
                    pending.append(root / "api/routes" / f"{module}.py")
            elif isinstance(call, ast.For) and isinstance(call.target, ast.Name) and isinstance(call.iter, (ast.Tuple, ast.List)):
                if any(_is_router_mount(item) and isinstance(item.args[0], ast.Name)
                       and item.args[0].id == call.target.id for item in ast.walk(call)):
                    arguments.extend(call.iter.elts)
        for argument in arguments:
            imported_name = argument.value if isinstance(argument, ast.Attribute) else argument
            module = imports.get(ast.unparse(imported_name))
            if module is not None and module not in mounted:
                mounted.add(module)
                pending.append(root / "api/routes" / f"{module}.py")
    return mounted


def _is_router_mount(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and bool(node.args)
        and isinstance(node.args[0], (ast.Attribute, ast.Name))
    )
