import ast
from pathlib import Path


def _show_source() -> str:
    source = Path("ui/pages/05_form_management.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    show = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "show")
    return ast.get_source_segment(source, show) or ""


def test_form_management_uses_read_only_client_identity_for_fields_and_stats():
    show_source = _show_source()
    full_source = Path("ui/pages/05_form_management.py").read_text(encoding="utf-8")

    assert "clients.identity_status" not in show_source
    assert "clients.identity_status" not in full_source
    assert '"identity_status"] = "身分資格（唯讀） (identity_status)"' in show_source
    assert "o.get('identity_status')" in show_source
    assert "form_db_table_fields" in show_source
