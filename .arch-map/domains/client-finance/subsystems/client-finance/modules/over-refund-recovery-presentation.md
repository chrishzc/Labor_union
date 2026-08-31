# Module: over-refund-recovery-presentation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
呈現客戶退款超額追償的既有 Query／Preview／Apply 與 fresh owner readback。一般畫面只顯示案件、追償餘額、closed狀態、處理方式與安全錯誤；配對identity/version只保留在預設收合的技術操作欄位。不得改寫Client Finance完成predicate或建立虛構銀行入款。

## Implementation
- primary: `ui_react/src/components/ClientOverRefundRecoveryWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — Client Finance追償、結清與fresh readback規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/client_over_refund_recovery_workbench.test.tsx`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/modules/over-refund-recovery-presentation.md`

## Change triggers
Reconcile when over-refund recovery presentation、technical-operation disclosure、fresh completion oracle或focused test location changes。
