module: order-card-projection
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-card-projection.md
layout_status: custom_current
test_root: ui_react/src/tests/orders_page_real_data.test.tsx
test_root: ui_react/src/tests/challenger_g5_adversarial_suite.test.tsx
test_root: ui_react/src/tests/orders_no_fake_mutation.test.ts
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/

# Owned verification
- `orders_page_real_data.test.tsx` — 保護案件投影的typed readback、營運摘要、collapsed technical provenance、取消影響的business-first presentation、既有Orders workflow surface與媒合 server-backed filter policy。
- `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/orders_adapter.test.ts` — 保護 Orders card projection adapter 的 typed 欄位與缺件狀態映射。

- `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/order_intake_completion_entry.test.tsx` — 驗證未完成訂單可進入既有補件 drawer 並保留 typed 補件 before/after oracle。
