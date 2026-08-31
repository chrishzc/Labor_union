# Module: historical-payment-settlement-presentation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
在既有 Finance owner page 以 Staff Payables strict client 呈現 exact staff＋case historical Query／Preview／Confirm／Apply／fresh readback。正常銀行候選、stale、identity mismatch 或 outcome unknown 時 fail closed，不從 Client payment／Orders status 推定 payout。

## Implementation
- primary: `ui_react/src/components/HistoricalStaffPayoutWorkbench.tsx`
- client: `ui_react/src/api/staff_payables/historical_staff_payout_client.ts`
- composition: `ui_react/src/pages/FinancePage.tsx`

## Contracts
- `modules/historical-payment-settlement.md` — owner application/public contract。
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — owner work item 顯示於 owner page，`#anomalies` 只保留 15 個 current issue。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_staff_payout_workbench.test.tsx`

## Change triggers
Reconcile when owner-page placement、strict client endpoint、staff／case／selection、confirmation、fresh readback或test root changes。
