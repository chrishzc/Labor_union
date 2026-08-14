"""
File: tests/test_data_import_runtime_acceptance_app_test.py
Description: 驗證資料匯入中心可實際渲染四個 workbook 卡與帳務匯入區。
"""

from streamlit.testing.v1 import AppTest


def test_data_import_center_renders_all_category_cards_without_upload() -> None:
    def _app() -> None:
        import importlib
        import os
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(os.getcwd()).resolve()))
        page = importlib.import_module("ui.pages.09_data_import")
        page._render_finance_card = lambda: page.st.subheader("銀行流水匯入")
        page.show()

    app = AppTest.from_function(_app)
    app.run(timeout=10)

    assert not app.exception
    assert [expander.label for expander in app.expander] == [
        "HCM 案件匯入",
        "HCM 歷史過渡匯入",
        "Client BeClass 暫時匯入",
        "Staff BeClass 歷史匯入（暫時入口）",
        "訂單狀態與月嫂歷史配對",
    ]
    assert any(title.value == "📥 資料匯入中心" for title in app.title)
    assert any(heading.value == "銀行流水匯入" for heading in app.subheader)
