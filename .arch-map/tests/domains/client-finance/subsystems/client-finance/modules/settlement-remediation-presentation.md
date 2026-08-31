module: settlement-remediation-presentation
parent_subsystem: client-finance
architecture: ../../../../../../domains/client-finance/subsystems/client-finance/modules/settlement-remediation-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/client_settlement_remediation.test.tsx

# Owned verification
- `client_settlement_remediation.test.tsx` — 保護三碼exact dispatcher、partial-retain、fresh terminal readback與business-first closed presentation。
