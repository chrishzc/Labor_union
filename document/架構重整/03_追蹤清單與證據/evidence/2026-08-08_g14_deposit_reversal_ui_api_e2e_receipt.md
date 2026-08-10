# G14 Deposit Reversal UI API E2E Receipt

- Observed date: `2026-08-08`
- Test node: `tests/test_g14_deposit_reversal_ui_api_e2e.py::test_g14_panel_uses_real_http_preview_and_apply`
- Result: `1 passed`
- Isolation: generated `lu_test_g14_ui_*` database and `DROP DATABASE IF EXISTS` in the runner `finally` block.

The test drives the Order Finance deposit-reversal panel with a test Streamlit display. Its actual UI client calls the FastAPI deposit-reversal router through `TestClient`; the router constructs the real MySQL application. The final database assertions show the immutable receipt plus canonical reversal ledger rows and no legacy `client_payments` write.

Warnings were the existing `.pytest_cache` `WinError 183` and Starlette TestClient deprecation notice. Neither affected the test result.
