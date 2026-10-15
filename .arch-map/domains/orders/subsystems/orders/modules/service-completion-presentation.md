# Module: service-completion-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
一般工作台呈現 Orders-owned 預計服務完成時間與自動完工狀態，移除人工完工按鈕。既有 Preview／Apply 與恢復元件保留供既有 consumer 使用；不得改寫服務完成 eligibility、Orders state machine 或後續 Finance／Payables 結算責任。

## Implementation
- primary:
  - `ui_react/src/api/orders/order_service_completion_client.ts`
  - `ui_react/src/components/OrderServiceCompletionActions.tsx`
  - `ui_react/src/components/OrderAutomaticCompletionStatus.tsx` — completion status Query and owner readback；沒有 completion mutation。
  - `ui_react/src/adapters/orders/order_mutation_flow_store.ts` — per-case completion command／receipt recovery state。
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders服務完成與lifecycle owner規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/order_service_completion_actions.test.tsx`
- test_root: `ui_react/src/tests/order_service_completion_client.test.ts`
- test_root: `ui_react/src/tests/order_workbench_v2_service_completion.test.tsx` — automatic status、移除 manual completion、owner refresh callback。
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/service-completion-presentation.md`

## Change triggers
Reconcile when service-completion presentation、confirmation gating、fresh completion readback、closed error或focused test location changes。
