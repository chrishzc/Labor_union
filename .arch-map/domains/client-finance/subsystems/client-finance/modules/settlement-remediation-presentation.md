# Module: settlement-remediation-presentation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
定位既有客戶應收、一般退款與補助退還的owner Query／Preview／Apply工作台及其測試。Source／test仍保留三碼exact dispatcher、partial-retain與fresh terminal readback；這是既有實作證據，不代表三碼仍屬current Anomalies runtime產品。一般畫面呈現案件、義務類型、日期、金額、可核對銀行流水、處理結果與安全錯誤；account version、obligation identity與bank row identity不在一般操作畫面顯示。Owner allocation與settlement以Client Finance正式契約為準；Anomalies current範圍以第06份規格為準。

## Implementation
- primary: `ui_react/src/components/ClientSettlementRemediationWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — Client Finance obligations、immutable ledger／allocation及reconciliation Preview／Apply。
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — 客戶退款／補助退還與銀行根事實核銷契約。
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` §1–2 — current runtime只保留 `LINE-006`；舊三碼source／test不形成新的Anomalies產品需求。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/client_settlement_remediation.test.tsx`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/modules/settlement-remediation-presentation.md`

## Change triggers
Reconcile when settlement presentation、既有dispatcher、partial-retain、fresh terminal oracle、current owner contract／Anomalies範圍或focused test location changes。
