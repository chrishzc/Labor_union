# Module: current-issue-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現 `LINE-006` 與 import warning 的 current-only清單、typed detail與closed owner action descriptor。一般畫面只顯示問題代碼、負責流程、影響、去敏判斷資料、業務操作與移除條件；owner domain/version及Preview／Apply／completion predicate不在一般操作畫面顯示。LINE 通知人工重送先以 detail 綁定的案件與來源版本核對 owner timeline，再呼叫 owner Preview；只有具理由且明確確認後才能 Apply，完成後重查 current facts。不得建立generic resolve、改寫owner predicate或以UI狀態移除current issue。

## Implementation
- primary: `ui_react/src/pages/CurrentAnomaliesPage.tsx`
- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`
- `ui_react/src/api/line/notification_manual_replay_client.ts`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `infrastructure/mysql/import_warning_tracking_repository.py`
- `api/routes/import_warning_tracking.py`
- `api/schemas/import_warning_tracking.py`
- `ui_react/src/api/anomalies/anomaly_query_schemas.ts`

## Dependencies
- outbound: `external-integration/line` — 查詢案件通知 timeline，並執行 typed manual replay Preview／Apply。

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — LINE-006 current-only Query、detail、owner action與recheck契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/current_anomalies_page.test.tsx`
- test_root: `ui_react/src/tests/line_notification_manual_replay_client.test.ts`
- test_root: `ui_react/src/tests/current_anomaly_query_client.test.ts`
- test_root: `ui_react/src/tests/anomaly_query_adapter.test.ts`
- test_root: `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- test_root: `tests/test_import_warning_tracking.py`
- test_root: `tests/test_import_warning_tracking_api.py`
- integration_root: `ui_react/src/tests/anomalies_entry_cutover.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md`

## Change triggers
Reconcile when current-only list/detail presentation、owner action descriptor、recheck removal copy或focused test location changes。
