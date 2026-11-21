# Module: current-issue-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
2026-10-16 最新人工裁決直接退役管理端「異常審核」頁、導覽與專用鈴鐺入口，不新增替代清單，也不搬移逐筆略過或 LINE 人工重送操作。既有 anomaly／import warning Query、owner mutation client、後端 Q/P/A、audit、receipt 與資料保留；頁面退役不代表業務問題已解除。舊 `#anomalies` 依 App 既有未知 hash 規則顯示待辦看板。

## Implementation
- primary: `ui_react/src/App.tsx` — 不再掛載異常審核。
- `ui_react/src/components/MasterLayout.tsx` — 不再宣告頁面、導覽或專用鈴鐺入口。
- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`
- `ui_react/src/api/line/notification_manual_replay_client.ts`
- `ui_react/src/api/anomalies/import_warning_skip_client.ts`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `infrastructure/mysql/import_warning_tracking_repository.py`
- `api/routes/import_warning_tracking.py`
- `api/schemas/import_warning_tracking.py`
- `ui_react/src/api/anomalies/anomaly_query_schemas.ts`
- `ui_react/src/api/anomalies/anomaly_query_client.ts` — 匯入警示 Query 與 wait-only referral，不再提供工作簿修正 command descriptor。

## Dependencies
- outbound: `case-import/hcm-current-workbook-import` — HCM 欄位清單使用 canonical current reviews；任一未解決欄位的人工略過經 Case Import Preview／Apply 保存 disposition 並重查，不使用 legacy tracking 作已綁定欄位解除判定。
- outbound: `clients/client-profile/profile-change` — 每一可補欄位提供案件與欄位深連結；服務方式使用 `service_type` 深連結；原工作簿修正入口已退役，無編輯入口的欄位仍可逐筆略過。
- outbound: `external-integration/line` — 查詢案件通知 timeline，並執行 typed manual replay 或 snapshot-bound warning skip Preview／Apply。

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — LINE-006 current-only Query、detail、owner action與recheck契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_notification_manual_replay_client.test.ts`
- test_root: `ui_react/src/tests/import_warning_skip_client.test.ts`
- test_root: `ui_react/src/tests/current_anomaly_query_client.test.ts`
- test_root: `ui_react/src/tests/anomaly_query_adapter.test.ts`
- test_root: `ui_react/src/tests/anomaly_query_client.test.ts` — 既有 typed query consumer 與 closed runtime decoding 契約；沿用本 module 的 custom_current placement。
- test_root: `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- test_root: `tests/test_import_warning_tracking.py`
- test_root: `tests/test_import_warning_tracking_api.py`
- integration_root: `ui_react/src/tests/anomalies_entry_cutover.test.tsx`
- 退役入口回歸（模擬 UI，L38–50）：異常審核不再出現在管理端導覽或頁面對照表，專用捷徑也不顯示；既有帳號權限入口仍可見。
- 舊雜湊回歸（同檔 L52–62）：`#anomalies`、`#/anomalies` 都導回既有待辦看板，不渲染「異常審核」；僅在這組模擬請求的斷言中，請求路徑全為系統狀態。
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md`

## Change triggers
Reconcile when retired management entry、retained API client contract或focused verification paths change。
