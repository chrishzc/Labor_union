module: historical-baseline-presentation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/historical-baseline-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/historical_operational_baseline_readback.test.tsx

# Owned verification
- `historical_operational_baseline_readback.test.tsx` — 保護Orders唯讀Query、closed step labels、collapsed provenance、closed unavailable與案件切換stale response discard。
