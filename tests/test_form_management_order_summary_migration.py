"""Guard the Form Management page against legacy full-list callers."""

from pathlib import Path


SHELL_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "05_form_management.py"


def test_form_management_uses_typed_bounded_orders_and_context_queries():
    source = SHELL_FILE.read_text(encoding="utf-8")

    assert "OrderSummaryApiClient" in source
    assert "FormManagementApiClient" in source
    assert '"/api/v1/orders"' not in source
    assert '"/api/v1/clients"' not in source
    assert "form_management_summary_after_case_no" in source
