# Module: overpayment-recovery-presentation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
呈現月嫂超額付款追償的既有 Query／Preview／Apply、結果重查與fresh owner readback。一般畫面只顯示追償餘額、closed狀態、處理方式與安全錯誤；matching identity/version只保留在預設收合的技術操作欄位。不得改寫Staff Payables追償完成predicate或建立虛構入款。

## Implementation
- primary: `ui_react/src/components/StaffOverpaymentRecoveryActions.tsx`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — Staff Payables超額付款追償與結清規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/staff_overpayment_recovery_actions.test.tsx`
- routing: `.arch-map/tests/domains/staff-payables/subsystems/staff-payables/modules/overpayment-recovery-presentation.md`

## Change triggers
Reconcile when overpayment-recovery presentation、safe result requery、fresh completion oracle或focused test location changes。
