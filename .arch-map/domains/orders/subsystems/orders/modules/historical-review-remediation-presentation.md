# Module: historical-review-remediation-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
呈現歷史訂單review更正的既有Query／Preview／Confirm／Apply與fresh owner readback。一般畫面只顯示案件、欄位衝突、檔案要求、業務處置與安全錯誤；版本、digest、fingerprint、receipt identity及issue code只保留在預設收合的技術詳情。不得改寫Orders review、remediation disposition或原警示解除predicate。

## Implementation
- primary: `ui_react/src/components/HistoricalOrderReviewRemediationWorkbench.tsx`

## Dependencies
- inbound: `global/application-shell/module:data-import-composition` — historical needs-review receipt 以既有 review identity 直接開啟工作台。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — 歷史review更正來源重新匯入與owner readback規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_order_review_remediation.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/historical-review-remediation-presentation.md`

## Change triggers
Reconcile when historical review remediation presentation、safe retry、fresh alert readback或focused test location changes。
