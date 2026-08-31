module: overpayment-recovery-presentation
parent_subsystem: government-subsidy
architecture: ../../../../../../domains/government-subsidy/subsystems/government-subsidy/modules/overpayment-recovery-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/government_overpayment_recovery_workbench.test.tsx

# Owned verification
- `government_overpayment_recovery_workbench.test.tsx` — 保護Preview gate、input invalidation、stale refresh、receipt-only不完成、double readback與business-first closed presentation。
