"""Task 97 LINE commit ownership and provider-boundary regressions."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "subsystems/line/client_binding_application.py",
    "subsystems/line/identity_management_application.py",
    "subsystems/line/identity_review_workflow.py",
    "subsystems/line/media_archive.py",
    "subsystems/line/order_group_application.py",
    "subsystems/line/rich_menu_publication_workflow.py",
    "subsystems/line/user_lifecycle.py",
)


def test_line_legacy_workflows_do_not_commit_or_rollback_raw_connections() -> None:
    """Raw connection transaction ownership is forbidden in LINE workflows."""

    violations: list[str] = []
    for relative_path in TARGETS:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"begin", "commit", "rollback"}:
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in {"conn", "connection"}:
                violations.append(f"{relative_path}:{node.lineno}:{node.func.attr}")
    assert violations == [], "raw connection transaction calls: " + ", ".join(violations)


def test_rich_menu_generated_asset_is_linked_by_completion_transaction() -> None:
    source = (ROOT / "subsystems/line/rich_menu_publication_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "UPDATE line_rich_menu_publications SET image_asset_id=%s WHERE id=%s" not in source
    assert "def _complete_publication" in source
    assert "image_asset_id=%s" in source
