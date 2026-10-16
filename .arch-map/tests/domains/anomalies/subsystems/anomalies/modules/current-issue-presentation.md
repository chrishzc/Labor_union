module: current-issue-presentation
parent_subsystem: anomalies
architecture: ../../../../../../domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/line_notification_manual_replay_client.test.ts
test_root: ui_react/src/tests/anomaly_query_adapter.test.ts
test_root: ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts
test_root: tests/test_import_warning_tracking.py
test_root: tests/test_import_warning_tracking_api.py
integration_root: ui_react/src/tests/anomalies_entry_cutover.test.tsx

# Owned verification
- `line_notification_manual_replay_client.test.ts` — 保護來源識別、嚴格 receipt 解碼及 owner Preview／Apply transport contract。
- `anomalies_entry_cutover.test.tsx` — 保護異常審核導覽與專用鈴鐺入口已移除，舊 hash 沿用待辦看板 fallback，且不再查詢異常或匯入警示清單。
