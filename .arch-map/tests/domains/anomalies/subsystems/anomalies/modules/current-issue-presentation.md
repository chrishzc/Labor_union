module: current-issue-presentation
parent_subsystem: anomalies
architecture: ../../../../../../domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/current_anomalies_page.test.tsx
test_root: ui_react/src/tests/line_notification_manual_replay_client.test.ts
test_root: ui_react/src/tests/anomaly_query_adapter.test.ts
test_root: ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts
test_root: tests/test_import_warning_tracking.py
test_root: tests/test_import_warning_tracking_api.py
integration_root: ui_react/src/tests/anomalies_entry_cutover.test.tsx

# Owned verification
- `current_anomalies_page.test.tsx` — 保護current-only list/detail readback、no-generic-resolve、LINE owner Preview／確認式 Apply 與business-first closed presentation。
- `line_notification_manual_replay_client.test.ts` — 保護來源識別、嚴格 receipt 解碼及 owner Preview／Apply transport contract。
- `anomalies_entry_cutover.test.tsx` — 保護authenticated `#anomalies` application composition只接受LINE-006 current contract與GET-only detail readback。
