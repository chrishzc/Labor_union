"""
File: test_react_streamlit_entry_rollback.py
Description: 驗證只保留資料匯入的 Streamlit compatibility deep link。
"""

from ui import app


def test_streamlit_compatibility_query_accepts_only_data_import():
    assert app.resolve_rollback_query("entry=data-import") == (
        "📥 資料匯入中心",
        None,
    )


def test_streamlit_compatibility_query_rejects_retired_or_extra_input():
    for query in (
        "entry=orders",
        "entry=scheduling&view=calendar",
        "entry=scheduling&view=staff-directory",
        "entry=finance",
        "entry=form-management&view=order-tracker",
        "entry=anomalies",
        "entry=line-management",
        "entry=system-status",
        "entry=data-browser",
        "entry=access-management",
        "entry=unknown",
        "entry=data-import&view=x",
        "entry=data-import&token=secret",
        "entry=DATA-IMPORT",
    ):
        assert app.resolve_rollback_query(query) is None
