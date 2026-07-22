import ast
from pathlib import Path


def _render_editor_source() -> str:
    source_path = Path("ui/pages/04_edit_order.py")
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    render_editor = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "render_editor"
    )
    return ast.get_source_segment(source, render_editor) or ""


def test_edit_order_uses_explicit_sync_preview_apply_and_never_direct_writes():
    render_source = _render_editor_source()

    assert "/assignment-synchronization/preview" in render_source
    assert "/assignment-synchronization/apply" in render_source
    assert "/assignment-schedules" in render_source
    assert '"remove_schedule_ids"' in render_source
    assert "db_service.update_order_full_details" not in render_source
    assert "db_service.update_order_status" not in render_source


def test_edit_order_requires_explicit_operator_and_exact_removal_confirmation():
    render_source = _render_editor_source()

    assert "applied_by.strip()" in render_source
    assert "set(selected_removal_ids)" in render_source
    assert "required_schedule_removals" in render_source


def test_edit_order_uses_read_only_client_identity_and_keeps_deposit_date_nullable():
    render_source = _render_editor_source()

    assert "clients.identity_status" not in render_source
    assert "client_identity_status = target_order.get('identity_status')" in render_source
    assert '"身分資格（唯讀）"' in render_source
    assert '"deposit_date": w_dep_due_date.isoformat() if w_dep_due_date else None' in render_source
    assert '"💾 確定儲存並套用同步"' in render_source
