# Test Root: orders/cancellation

## Parent
- subsystem: orders
- domain: orders
- architecture: ../../../../../../domains/orders/subsystems/orders/modules/cancellation.md

## Test role
- `tests/domains/orders/subsystems/orders/modules/cancellation/` — cancellation owner-local oracles.
- `tests/domains/orders/subsystems/orders/integration/` — cancellation cross-domain integration oracles.

## Current coverage
- `modules/cancellation/test_historical_mid_service_cancellation.py` — historical cancellation-origin rows only enter one-time remediation when confirmed service-day facts exist.
- `test_cancelled_order_reentry_guard.py` — 已生效取消不得再次建立 cancellation candidate，回 typed conflict 且不開啟寫入 UoW。
- `test_order_cancellation_cross_domain_chain.py` — Preview／Apply 持久化 canonical cross-owner chain，same-key replay 不重複寫入。
- `test_order_cancellation_receipt_route.py` — receipt readback、認證與 cross-case not-found contract。
- `ui_react/src/tests/orders_page_real_data.test.tsx` — cancellation Query／Preview／Apply UI gating；一般已取消案件維持 disabled，只有 server 明示的歷史服務中補登例外可進入逐日確認與 Preview／Apply。
- `ui_react/src/tests/order_workbench_v2_cancellation.test.tsx` — cancellation Query／Preview／readback 的 case-switch、abort 與 owner identity UI guards。
- `ui_react/src/tests/order_workbench_v2_reopen.test.tsx` — controlled reopen Preview／readback 的 case isolation、abort 與 owner identity UI guards。
- `ui_react/src/tests/order_cancellation_client.test.ts` — typed cancellation transport 的 schema、case identity、idempotency header 與 retained actor pre-POST guard。
