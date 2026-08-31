module: order-tracker-presentation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-tracker-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/order_tracker_request_budget.test.tsx

# Owned verification
- `order_tracker_request_budget.test.tsx` — 保護summary initial load、explicit retry request budget、stale response suppression及closed main-list error presentation。
