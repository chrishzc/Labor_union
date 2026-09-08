module: order-card-projection
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-card-projection.md
layout_status: custom_current
test_root: ui_react/src/tests/order_workbench_v2_page.test.tsx
test_root: ui_react/src/tests/orders_no_fake_mutation.test.ts
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/

# Owned verification
- `order_workbench_v2_page.test.tsx` — 保護 current Workbench 的 typed projection、正式入口與 closed presentation。
- `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/orders_adapter.test.ts` — 保護 Orders card projection adapter 的 typed 欄位與缺件狀態映射。

- `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/order_intake_completion_entry.test.tsx` — 驗證未完成訂單可進入既有補件 drawer 並保留 typed 補件 before/after oracle。
