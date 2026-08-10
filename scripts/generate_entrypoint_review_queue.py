"""Generate the entry-point review queue without recording runtime usage."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence" / "entrypoint_review_queue_v1.jsonl"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def discover_entrypoints() -> list[dict[str, object]]:
    entries = [*_discover_api_entries(), *_discover_ui_entries(), *_discover_cli_entries()]
    return sorted(entries, key=lambda entry: str(entry["entry_id"]))


def build_review_queue() -> list[dict[str, object]]:
    existing = _existing_entries()
    return [_merge_reviewed_entry(entry, existing) for entry in discover_entrypoints()]


def main() -> int:
    entries = build_review_queue()
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(_render_queue(entries), encoding="utf-8")
    review_count = sum(entry["status"] == "review_required" for entry in entries)
    print(f"entrypoint_review_queue entries={len(entries)} review_required={review_count}")
    return 0


def _discover_api_entries() -> list[dict[str, object]]:
    paths = [ROOT / "api/main.py", *(ROOT / "api/routes").glob("*.py"), ROOT / "line/line_bot.py"]
    return [entry for path in paths if path.name != "__init__.py" for entry in _api_entries(path)]


def _api_entries(path: Path) -> list[dict[str, object]]:
    tree = _tree(path)
    prefix_by_name = _router_prefixes(tree)
    return [
        _new_entry("api", f"{method.upper()} {_route_path(prefix_by_name, decorator)}", path)
        for function in tree.body
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in function.decorator_list
        for method in [_http_method(decorator)]
        if method is not None
    ]


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    return {
        target.id: _keyword_string(value, "prefix")
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        for value in [node.value]
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in {"APIRouter", "FastAPI"}
    }


def _http_method(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    method = decorator.func.attr.lower()
    return method if method in HTTP_METHODS else None


def _route_path(prefix_by_name: dict[str, str], decorator: ast.expr) -> str:
    assert isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
    owner = decorator.func.value
    prefix = prefix_by_name.get(owner.id, "") if isinstance(owner, ast.Name) else ""
    suffix = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str) else ""
    return f"{prefix}{suffix}" or "/"


def _discover_ui_entries() -> list[dict[str, object]]:
    return [_new_entry("ui", path.name, path) for path in (ROOT / "ui/pages").glob("*.py") if _page_title(path)]


def _page_title(path: Path) -> str | None:
    return next((value.value for node in _tree(path).body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id == "title" for value in [node.value] if isinstance(value, ast.Constant) and isinstance(value.value, str)), None)


def _discover_cli_entries() -> list[dict[str, object]]:
    return [_new_entry("cli", path.relative_to(ROOT).as_posix(), path) for path in (ROOT / "scripts").rglob("*.py") if _has_main_guard(path)]


def _has_main_guard(path: Path) -> bool:
    return any(isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__" for node in _tree(path).body)


def _new_entry(kind: str, label: str, path: Path) -> dict[str, object]:
    return {"entry_id": f"{kind}:{label}", "kind": kind, "source_path": path.relative_to(ROOT).as_posix(), "status": "review_required"}


def _existing_entries() -> dict[str, dict[str, object]]:
    if not QUEUE_PATH.exists():
        return {}
    return {
        str(entry["entry_id"]): entry
        for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines()
        if line
        for entry in [json.loads(line)]
    }


def _merge_reviewed_entry(entry: dict[str, object], existing: dict[str, dict[str, object]]) -> dict[str, object]:
    reviewed = existing.get(str(entry["entry_id"]), {})
    if reviewed.get("status") in {None, "review_required"}:
        return entry
    return {**entry, **{key: value for key, value in reviewed.items() if key not in {"kind", "source_path"}}}


def _keyword_string(call: ast.Call, keyword: str) -> str:
    value = next((item.value for item in call.keywords if item.arg == keyword), None)
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ""


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _render_queue(entries: list[dict[str, object]]) -> str:
    return "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)


if __name__ == "__main__":
    raise SystemExit(main())
