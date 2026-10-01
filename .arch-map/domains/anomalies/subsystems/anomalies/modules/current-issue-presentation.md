# Module: current-issue-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現 `LINE-006` 與 import warning 的 current-only清單、typed detail與closed owner action descriptor。一般畫面只顯示問題代碼、負責流程、影響、去敏判斷資料、業務操作與移除條件；owner domain/version及Preview／Apply／completion predicate不在一般操作畫面顯示。LINE 通知人工重送先以 detail 綁定的案件與來源版本核對 owner timeline，再呼叫 owner Preview。2026-10-01 人工裁決允許全部目前警示逐筆確認略過，HCM 欄位、import occurrence 與 LINE 失敗各走既有 owner Q/P/A、audit 與 receipt；不由 UI 假移除或改寫 root。不提供批次略過。

## Implementation
- primary: `ui_react/src/pages/CurrentAnomaliesPage.tsx`
- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`
- `ui_react/src/api/line/notification_manual_replay_client.ts`
- `ui_react/src/api/anomalies/import_warning_skip_client.ts`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `infrastructure/mysql/import_warning_tracking_repository.py`
- `api/routes/import_warning_tracking.py`
- `api/schemas/import_warning_tracking.py`
- `ui_react/src/api/anomalies/anomaly_query_schemas.ts`

## Dependencies
- outbound: `case-import/hcm-current-workbook-import` — HCM 欄位清單使用 canonical current reviews；任一未解決欄位的人工略過經 Case Import Preview／Apply 保存 disposition 並重查，不使用 legacy tracking 作已綁定欄位解除判定。
- outbound: `clients/client-profile/profile-change` — 每一可補欄位提供案件與欄位深連結；原工作簿修正工作台保留次要入口。
- outbound: `external-integration/line` — 查詢案件通知 timeline，並執行 typed manual replay 或 snapshot-bound warning skip Preview／Apply。

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — LINE-006 current-only Query、detail、owner action與recheck契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/current_anomalies_page.test.tsx`
- test_root: `ui_react/src/tests/line_notification_manual_replay_client.test.ts`
- test_root: `ui_react/src/tests/import_warning_skip_client.test.ts`
- test_root: `ui_react/src/tests/current_anomaly_query_client.test.ts`
- test_root: `ui_react/src/tests/anomaly_query_adapter.test.ts`
- test_root: `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- test_root: `tests/test_import_warning_tracking.py`
- test_root: `tests/test_import_warning_tracking_api.py`
- integration_root: `ui_react/src/tests/anomalies_entry_cutover.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md`

## Change triggers
Reconcile when current-only list/detail presentation、owner action descriptor、recheck removal copy或focused test location changes。
