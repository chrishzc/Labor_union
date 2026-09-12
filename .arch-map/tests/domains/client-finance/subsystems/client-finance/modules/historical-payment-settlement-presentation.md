module: historical-payment-settlement-presentation
parent_subsystem: client-finance
architecture: ../../../../../../domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/historical_client_payment_workbench.test.tsx
test_root: ui_react/src/tests/finance_query_transport_identity.test.ts
test_root: ui_react/src/tests/finance_query_clients.test.ts
test_root: ui_react/src/tests/finance_request_lifecycle.test.tsx
integration_root: ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement-presentation/

# Owned verification
- `historical_client_payment_workbench.test.tsx` — Client Finance owner page 的 exact Query／Preview／Confirm／Apply／fresh readback 閉環。
- `finance_query_page.test.tsx` — Finance owner page 的 query composition 與歷史人工收款入口資格。
- `finance_query_clients.test.ts` — FinancePage 使用的 strict query client response identity 與 aggregate contract。
- `finance_request_lifecycle.test.tsx` — FinancePage query／download 在 tab、month 與 unmount 時的 request lifecycle。
