# Module: payout-remediation-presentation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
呈現月嫂付款核銷的既有 Query／Preview／Apply、背景處理與 fresh owner readback。一般畫面只顯示應付款、銀行入帳、處理狀態與安全重試等業務語意，不顯示 staff／obligation identity、owner version、job ID、idempotency key或raw error。銀行對帳的 `FinanceImportCorrectionForm` 可帶入固定流水與同一月嫂的選定款項，處理不足額／超額；選定款項全數結清才通知解除。不得改寫Staff Payables完成predicate或發動銀行匯款。

## Implementation
- primary: `ui_react/src/components/StaffPayoutRemediationWorkbench.tsx`
- transport: `ui_react/src/api/staff_payables/staff_payout_remediation_client.ts`、`ui_react/src/api/staff_payables/staff_payout_remediation_schemas.ts`
- 原銀行入口帶入日期、實付、對象及摘要；共用 Query 的 `funding_portions` 顯示自備款／補助款各自待付。確認前以正式 Preview 顯示手續費及剩餘款，成功後回讀未清補助，不由畫面推斷整案結清。
- 永豐核銷方式可明選「補助方案一：核銷自備款，補助款保留待付」；帶 `confirm_subsidy_split` 至原 payout endpoint，必須取得含正式 T／S／兩來源待付及日期的預覽後再確認。方案／分期與付款一起成功才回讀並提示已保存；未知結果保留原背景命令，不拆成前端兩次儲存。

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — Staff Payables owner workflow與結清條件。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/staff_payout_remediation_workbench.test.tsx`
- test_root: `ui_react/src/tests/staff_payout_remediation_client.test.ts`
- routing: `.arch-map/tests/domains/staff-payables/subsystems/staff-payables/modules/payout-remediation-presentation.md`

## Change triggers
Reconcile when payout-remediation presentation、safe-retry wording、fresh readback oracle或focused test location changes。
