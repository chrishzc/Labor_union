module: finance-correction-presentation
parent_subsystem: anomalies
architecture: ../../../../../../domains/anomalies/subsystems/anomalies/modules/finance-correction-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/anomalies_finance_correction_flow.test.tsx

# Owned verification
- `anomalies_finance_correction_flow.test.tsx` — 保護既有更正完成 predicate、安全重查、不重送 Apply，以及 closed 業務錯誤投影。
