"""Workflow tests for the deposit reversal Streamlit panel."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from ui.pages.order import client_deposit_reversal_panel as panel


class _Streamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.button_values = {}
        self.rerun_called = False

    def markdown(self, *_args, **_kwargs) -> None:
        pass

    def caption(self, *_args, **_kwargs) -> None:
        pass

    def number_input(self, *_args, **_kwargs) -> int:
        return 42

    def date_input(self, *_args, **_kwargs) -> date:
        return date(2026, 8, 8)

    def button(self, _label, *, key) -> bool:
        return self.button_values.get(key, False)

    def json(self, *_args, **_kwargs) -> None:
        pass

    def text_input(self, *_args, **_kwargs) -> str:
        return "bank receipt was reversed"

    def success(self, *_args, **_kwargs) -> None:
        pass

    def error(self, *_args, **_kwargs) -> None:
        pass

    def rerun(self) -> None:
        self.rerun_called = True


class _Client:
    def __init__(self) -> None:
        self.preview_calls = []
        self.apply_calls = []
        self.preview_value = SimpleNamespace(
            account_version=4,
            candidate={"reversal_amount_ntd": 1200},
            preview_fingerprint="a" * 64,
        )

    def preview(self, *args, **kwargs):
        self.preview_calls.append((args, kwargs))
        return self.preview_value

    def apply(self, *args, **kwargs):
        self.apply_calls.append((args, kwargs))
        return SimpleNamespace(reversal_amount_ntd=1200, account_version=5)


def test_panel_applies_the_server_preview_without_ui_business_calculation(monkeypatch):
    streamlit = _Streamlit()
    client = _Client()
    case_no = "C-14"
    preview_key = f"deposit_reversal_preview_{case_no}"
    apply_key = f"deposit_reversal_apply_{case_no}"

    monkeypatch.setattr(panel, "st", streamlit)
    monkeypatch.setattr(panel, "_client", lambda: client)
    streamlit.button_values[preview_key] = True
    panel.render_client_deposit_reversal_panel(case_no)

    assert client.preview_calls[0][0][1:] == (42, date(2026, 8, 8))
    assert f"deposit_reversal_preview:{case_no}" in streamlit.session_state
    streamlit.button_values[preview_key] = False
    streamlit.button_values[apply_key] = True
    panel.render_client_deposit_reversal_panel(case_no)

    assert client.apply_calls[0][0][3] is client.preview_value
    assert client.apply_calls[0][1]["reason"] == "bank receipt was reversed"
    assert f"deposit_reversal_preview:{case_no}" not in streamlit.session_state
    assert streamlit.rerun_called is True
