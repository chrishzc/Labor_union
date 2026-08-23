"""
File: test_react_streamlit_entry_rollback.py
Description: 驗證 React 對應的 Streamlit rollback deep link 僅接受凍結 mapping。
"""

from ui import app


def test_streamlit_rollback_query_accepts_only_frozen_pairs():
    assert app.resolve_rollback_query("entry=scheduling&view=calendar") == (
        "多月嫂排班",
        "calendar",
    )
    assert app.resolve_rollback_query("entry=scheduling&view=staff-directory") == (
        "多月嫂排班",
        "staff-directory",
    )
    assert app.resolve_rollback_query("entry=finance") == ("💰 帳務作業中心", None)


def test_streamlit_rollback_query_rejects_unknown_or_extra_input():
    for query in (
        "entry=unknown",
        "entry=finance&view=x",
        "entry=finance&token=secret",
        "entry=FINANCE",
    ):
        assert app.resolve_rollback_query(query) is None
