# Module: overpayment-recovery-presentation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
呈現GOVSUB-006既有Query／Preview／Confirm／Apply、stale refresh、receipt-only不完成及owner＋current-issue雙重readback。一般畫面只顯示closed狀態、剩餘金額、合法處置、補助標的、政府退款對象與安全錯誤；owner version與source references只保留在預設收合技術詳情。不得改寫offset／return互斥、terminal predicate或重送Apply。

## Implementation
- primary: `ui_react/src/components/GovernmentOverpaymentRecoveryWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md` — 政府溢撥offset／return、stale、idempotency與readback規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/government_overpayment_recovery_workbench.test.tsx`
- routing: `.arch-map/tests/domains/government-subsidy/subsystems/government-subsidy/modules/overpayment-recovery-presentation.md`

## Change triggers
Reconcile when GOVSUB-006 presentation、stale refresh、double-readback completion oracle或focused test location changes。
