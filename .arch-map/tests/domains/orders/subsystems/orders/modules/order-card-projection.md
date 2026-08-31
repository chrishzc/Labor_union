module: order-card-projection
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-card-projection.md
layout_status: custom_current
test_root: ui_react/src/tests/orders_page_real_data.test.tsx

# Owned verification
- `orders_page_real_data.test.tsx` — 保護案件投影的typed readback、營運摘要、collapsed technical provenance、取消影響的business-first presentation與既有Orders workflow surface。
