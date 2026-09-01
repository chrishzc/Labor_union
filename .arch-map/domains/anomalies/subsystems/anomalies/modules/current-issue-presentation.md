# Module: current-issue-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現唯一 `LINE-006` current-only清單、typed detail與closed owner action descriptor。一般畫面只顯示問題代碼、負責流程、影響、去敏判斷資料、業務操作與移除條件；owner domain/version及Preview／Apply／completion predicate只保留在預設收合技術詳情。不得建立generic resolve、改寫owner predicate或以UI狀態移除current issue。

## Implementation
- primary: `ui_react/src/pages/CurrentAnomaliesPage.tsx`
- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — LINE-006 current-only Query、detail、owner action與recheck契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/current_anomalies_page.test.tsx`
- test_root: `ui_react/src/tests/current_anomaly_query_client.test.ts`
- test_root: `ui_react/src/tests/anomaly_query_adapter.test.ts`
- test_root: `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- integration_root: `ui_react/src/tests/anomalies_entry_cutover.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md`

## Change triggers
Reconcile when current-only list/detail presentation、owner action descriptor、recheck removal copy或focused test location changes。
