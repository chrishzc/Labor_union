module: service-completion-presentation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/service-completion-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/order_service_completion_actions.test.tsx

# Owned verification
- `order_service_completion_actions.test.tsx` — 保護非服務中案件read-only、Preview／Confirm／Apply gating、completion readback及closed error presentation。
