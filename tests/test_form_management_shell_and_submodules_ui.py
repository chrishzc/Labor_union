"""Direct tests for Form Management page shell and submodules wiring."""

from __future__ import annotations

import ast
from pathlib import Path

SHARED_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "form_management" / "shared.py"
TAB2_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "form_management" / "tab2_template_library.py"
TAB3_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "form_management" / "tab3_contract_management.py"
SHELL_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "05_form_management.py"


def test_form_management_submodules_exist():
    assert SHARED_FILE.exists()
    assert TAB2_FILE.exists()
    assert TAB3_FILE.exists()
    assert SHELL_FILE.exists()


def test_form_management_shell_imports_and_delegates_to_retained_tabs():
    shell_text = SHELL_FILE.read_text(encoding="utf-8")
    assert "from ui.pages.form_management.tab2_template_library import _render_tab2_template_library" in shell_text
    assert "from ui.pages.form_management.tab3_contract_management import _render_tab3_contract_management" in shell_text
    assert "tab1_form_builder" not in shell_text

    tree = ast.parse(shell_text)
    shell_func = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_form_management_page_shell"
    )
    shell_src = ast.get_source_segment(shell_text, shell_func) or ""

    assert "_render_tab2_template_library(" in shell_src
    assert "_render_tab3_contract_management(" in shell_src
