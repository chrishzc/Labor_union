module: delivery-task-presentation
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/delivery-task-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/line_delivery_task_workbench.test.tsx

# Owned verification
- `line_delivery_task_workbench.test.tsx` — 保護server pagination、allowlisted filters、stale response suppression、detail navigation及closed query error presentation。
