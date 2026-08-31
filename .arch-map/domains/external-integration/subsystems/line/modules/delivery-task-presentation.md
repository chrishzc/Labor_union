# Module: delivery-task-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned delivery task的既有server pagination、allowlisted filter、masked item與detail navigation。一般畫面不得顯示query error code或raw backend／provider detail；不得改寫delivery intent／receipt、worker、retry或provider transport責任。

## Implementation
- primary: `ui_react/src/components/LineDeliveryTaskWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE delivery與provider邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_delivery_task_workbench.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/delivery-task-presentation.md`

## Change triggers
Reconcile when delivery-task presentation、pagination/filter/stale suppression、closed error或focused test location changes。
