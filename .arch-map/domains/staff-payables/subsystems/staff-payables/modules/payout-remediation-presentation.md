# Module: payout-remediation-presentation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
呈現逾期應付款核銷的既有 Query／Preview／Apply、背景處理與 fresh owner readback。一般畫面只顯示應付款、銀行入帳、處理狀態與安全重試等業務語意，不顯示 staff／obligation identity、owner version、job ID、idempotency key或raw error。不得改寫Staff Payables完成predicate或發動銀行匯款。

## Implementation
- primary: `ui_react/src/components/StaffPayoutRemediationWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — Staff Payables owner workflow與結清條件。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/staff_payout_remediation_workbench.test.tsx`
- routing: `.arch-map/tests/domains/staff-payables/subsystems/staff-payables/modules/payout-remediation-presentation.md`

## Change triggers
Reconcile when payout-remediation presentation、safe-retry wording、fresh readback oracle或focused test location changes。
