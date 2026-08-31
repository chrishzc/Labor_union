"""Task 97 guards for anomaly projection and outbox failure transaction ownership."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]

FAILURE_HELPERS = {
    "subsystems/case_import/beclass_import_outbox_consumer.py": "_mark_failed",
    "subsystems/finance_import/finance_import_anomaly_consumer.py": "_mark_failed",
    "subsystems/anomalies/hcm_import_review_outbox_consumer.py": "_mark_failed",
    "subsystems/case_import/hcm_resubmission_outbox_consumer.py": "_mark_failed",
    "subsystems/orders/historical_order_adoption_outbox_consumer.py": "_mark_failed",
    "subsystems/orders/historical_order_review_remediation_outbox_consumer.py": "_mark_failed",
}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _connection_transaction_calls(node: ast.AST) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"begin", "commit", "rollback"}
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "connection"
    ]


def test_failure_helpers_only_issue_failure_update() -> None:
    for relative_path, helper_name in FAILURE_HELPERS.items():
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        helper = _function(tree, helper_name)
        assert not _connection_transaction_calls(helper), relative_path
        owner = _function(tree, "_record_failure")
        assert any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "commit"
            for call in ast.walk(owner)
            if isinstance(call, ast.Call)
        ), relative_path
