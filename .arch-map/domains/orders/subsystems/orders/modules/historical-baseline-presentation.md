# Module: historical-baseline-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
呈現Orders-owned Historical Operational Baseline唯讀Query。一般畫面只顯示案件、目前作業步驟與closed步驟狀態；Orders identity/version、historical source event/version只留在預設收合技術詳情，typed error code不得穿透。不得提供mutation、推導不存在的owner event或改變stale-request protection。

## Implementation
- primary: `ui_react/src/components/HistoricalOperationalBaselineReadback.tsx`

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Historical Orders baseline與step projection規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_operational_baseline_readback.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/historical-baseline-presentation.md`

## Change triggers
Reconcile when historical baseline Query presentation、step labels、technical provenance、closed error、stale request guard或focused test location changes。
