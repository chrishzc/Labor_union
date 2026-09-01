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
- `ui_react/src/tests/orders_page_real_data.test.tsx` — cancellation Query／Preview／Apply UI gating 與已取消 disabled presentation。
