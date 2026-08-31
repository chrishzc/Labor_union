# Module: finance-correction-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現既有 Finance Import 更正 Preview、Apply、結果查詢與來源異常 fresh recheck；一般畫面只顯示 closed 業務訊息，不顯示 job、receipt、identity、fingerprint 或 transport detail。不得改寫 Finance 更正 workflow、完成 predicate 或 retry identity。

## Implementation
- primary: `ui_react/src/pages/AnomaliesPage.tsx`

## Contracts
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — Anomalies detail／recovery closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/anomalies_finance_correction_flow.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/finance-correction-presentation.md`

## Lifecycle
- `superseded_candidate`: retired anomaly presentation；若 source／test retirement完成，移除本 leaf及其 inbound route。

## Change triggers
Reconcile when Finance correction presentation、fresh recheck completion oracle或focused test location changes。
