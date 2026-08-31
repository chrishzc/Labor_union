module: overpayment-recovery-presentation
parent_subsystem: staff-payables
architecture: ../../../../../../domains/staff-payables/subsystems/staff-payables/modules/overpayment-recovery-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/staff_overpayment_recovery_actions.test.tsx

# Owned verification
- `staff_overpayment_recovery_actions.test.tsx` — 保護既有matching／collection／adjustment、配對不假解除、fresh terminal readback與business-first closed presentation。
