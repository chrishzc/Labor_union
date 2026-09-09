module: line-identity-maintenance-presentation
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/line-identity-maintenance-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/line_identity_maintenance_actions.test.tsx

# Owned verification
- `line_identity_maintenance_actions.test.tsx` — 保護 replacement Preview／Confirm／Apply、解除後訪客選單回復 retry、一般管理 UI 不呈現 manual-completion 分支，以及 closed error presentation。
