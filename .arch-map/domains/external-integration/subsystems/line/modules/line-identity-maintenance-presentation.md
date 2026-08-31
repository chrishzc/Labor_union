# Module: line-identity-maintenance-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned身分對象更正及既有解除失敗維護操作。一般畫面以closed業務訊息說明失敗，不得顯示typed error code或raw backend／provider detail；不得改寫replacement Apply、解除retry、manual-completion資格與雙重確認、Rich Menu provider邊界或callback語意。

## Implementation
- primary: `ui_react/src/components/LineIdentityMaintenanceActions.tsx`

## Contracts
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — replacement與解除維護契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_identity_maintenance_actions.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/line-identity-maintenance-presentation.md`

## Change triggers
Reconcile when identity-maintenance presentation、replacement／revocation controls、closed error或focused test location changes。
