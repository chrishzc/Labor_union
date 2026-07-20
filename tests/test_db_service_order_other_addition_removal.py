"""Acceptance coverage for the DbService order-field cleanup contract."""

from __future__ import annotations

import ast
from pathlib import Path


DB_SERVICE = Path(__file__).resolve().parents[1] / "services" / "db_service.py"


def _function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(DB_SERVICE.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert name in functions, f"missing DbService function: {name}"
    return functions[name]


def _function_source(name: str) -> str:
    source = DB_SERVICE.read_text(encoding="utf-8")
    segment = ast.get_source_segment(source, _function_node(name))
    assert segment is not None
    return segment


def test_get_order_by_case_no_never_selects_other_addition():
    source = _function_source("get_order_by_case_no")

    assert "other_addition" not in source
    assert "o.floor_fee" in source
    assert "_resolve_case_no(case_no)" in source


def test_create_order_has_no_other_addition_contract_and_keeps_floor_fee():
    node = _function_node("create_order")
    source = _function_source("create_order")
    argument_names = [argument.arg for argument in node.args.args]

    assert "other_addition" not in argument_names
    assert "other_addition" not in source
    assert "floor_fee" in argument_names
    assert "_resolve_case_no(case_no)" in source
    assert "INSERT IGNORE INTO client_payments" in source


def test_create_order_insert_placeholders_match_parameter_tuple():
    node = _function_node("create_order")
    inserts = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not call.args:
            continue
        query = call.args[0]
        if isinstance(query, ast.Constant) and isinstance(query.value, str) and "INSERT INTO orders" in query.value:
            inserts.append(call)

    assert len(inserts) == 1
    insert_call = inserts[0]
    query = insert_call.args[0].value
    parameters = insert_call.args[1]
    assert isinstance(parameters, ast.Tuple)
    assert query.count("%s") == len(parameters.elts)
