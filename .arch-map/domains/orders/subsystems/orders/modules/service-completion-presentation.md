# Module: service-completion-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
呈現Orders-owned服務完成的既有Preview／Confirm／Apply與完成回讀。一般畫面只顯示目前案件狀態、正式服務日、完成時刻、必要確認與closed結果；owner名稱、lifecycle controls、fingerprint、idempotency及receipt等技術資訊不得穿透。不得改寫服務完成 eligibility、Orders state machine或後續Finance／Payables結算責任。

## Implementation
- primary: `ui_react/src/components/OrderServiceCompletionActions.tsx`

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders服務完成與lifecycle owner規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/order_service_completion_actions.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/service-completion-presentation.md`

## Change triggers
Reconcile when service-completion presentation、confirmation gating、fresh completion readback、closed error或focused test location changes。
