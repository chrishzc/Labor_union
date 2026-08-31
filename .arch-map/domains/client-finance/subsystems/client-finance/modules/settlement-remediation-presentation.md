# Module: settlement-remediation-presentation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
呈現客戶逾期應收、一般退款與補助退還三碼的既有exact dispatcher、Query／Preview／Apply、partial-retain與fresh terminal readback。一般畫面只顯示案件、義務類型、日期、金額、可核對銀行流水、處理結果與安全錯誤；account version、obligation identity與bank row identity只保留在預設收合技術詳情。不得合併三碼predicate、推定allocation或以追蹤狀態解除提醒。

## Implementation
- primary: `ui_react/src/components/ClientSettlementRemediationWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — Client Finance銀行根事實、Q/P/A與逾期提醒規則。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260827-client-settlement-anomaly-remediation-spec.md` — 三碼exact dispatcher、partial-retain與terminal predicate。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/client_settlement_remediation.test.tsx`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/modules/settlement-remediation-presentation.md`

## Change triggers
Reconcile when settlement presentation、three-code dispatcher、partial-retain、fresh terminal oracle或focused test location changes。
