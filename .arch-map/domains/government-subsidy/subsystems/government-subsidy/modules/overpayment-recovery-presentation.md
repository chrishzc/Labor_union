# Module: overpayment-recovery-presentation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
呈現 GOVSUB-006 的 offset Query／Preview／Confirm／Apply、stale refresh、receipt-only 不完成及既有回讀確認。只接受合法抵扣標的；退回選項、政府退款對象及相關 Query 欄位已移除。一般畫面只顯示狀態、剩餘金額、抵扣標的與安全錯誤，owner version 與 source references 不在一般操作畫面顯示。

## Implementation
- primary: `ui_react/src/components/GovernmentOverpaymentRecoveryWorkbench.tsx`
- typed query decoder: `ui_react/src/api/government_subsidy/government_overpayment_recovery_schemas.ts`

## Contracts
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md` — 政府溢撥 offset、stale、idempotency 與 readback 規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/government_overpayment_recovery_workbench.test.tsx`
- test_root: `ui_react/src/tests/government_overpayment_recovery_client.test.ts`
- routing: `.arch-map/tests/domains/government-subsidy/subsystems/government-subsidy/modules/overpayment-recovery-presentation.md`

## Change triggers
Reconcile when GOVSUB-006 presentation、stale refresh、double-readback completion oracle或focused test location changes。
