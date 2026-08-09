# G14 Deposit Reversal UI Thin-Flow Receipt

- Observed date: `2026-08-08`
- UI client: `ui/api_clients/client_deposit_reversal_api_client.py`
- UI panel: `ui/pages/order/client_deposit_reversal_panel.py`
- Mount point: `ui/pages/order/tab3_finance.py`
- Tests: `tests/test_client_deposit_reversal_api_client.py` and `tests/test_client_deposit_reversal_panel.py`
- Result: `2 passed`

The UI client sends Preview to the canonical deposit-reversal endpoint and carries the server-provided account version and preview fingerprint into Apply with an Idempotency-Key and correlation ID. The panel presents the server candidate, does not derive amount or lifecycle intent, and applies the same Preview object before clearing its session state on success.

This receipt is not the G14 Global E2E proof. The remaining gap is one real HTTP plus Streamlit data-flow trace combined with the existing isolated MySQL reversal and receipt-reconciliation scenarios.

Source SHA-256:

- `ui/api_clients/client_deposit_reversal_api_client.py`: `3974a15014e74fd1c12bf31497002419f70e1aa9bddc344fd9d896576d6c9c3d`
- `ui/pages/order/client_deposit_reversal_panel.py`: `9210690b48dc4bffefa4e12deeeb7b91e6834e52f2a330856529accb2723f5ac`
- `ui/pages/order/tab3_finance.py`: `e532cde8fd18548de964e2b155e91935f76ca6e01ec5b6a9ab0c1a0c7243e7c1`
- `tests/test_client_deposit_reversal_api_client.py`: `cff6600d6f88fadc4e7d327d3da8601dcb12f4a972a85120690442604f23f7e8`
- `tests/test_client_deposit_reversal_panel.py`: `1520bfda5a1efc453eaa1a77c8e38001c2fc7f6a134d75a920787fef5ea41c1d`
