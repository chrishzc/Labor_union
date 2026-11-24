module: service-completion-presentation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/service-completion-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/order_service_completion_actions.test.tsx
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/service-completion-presentation/

# Owned verification
- `order_service_completion_actions.test.tsx` — 保護非服務中案件read-only、Preview／Confirm／Apply gating、completion readback及closed error presentation。
- `order_workbench_v2_service_completion.test.tsx` — 保護工作台自動完工狀態與 owner 回讀；單一月嫂手動開啟分配，多位正式月嫂自動展開，並保留各人月曆與換人連結。
