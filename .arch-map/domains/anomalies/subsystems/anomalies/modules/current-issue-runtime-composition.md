# Module: current-issue-runtime-composition

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
在既有durable recheck runtime組合owner-specific typed snapshot reader與Anomalies consumer；不新增owner
mutation、business predicate或public entry。

## Implementation
- `infrastructure/mysql/anomaly_runtime.py`
- `infrastructure/mysql/anomaly_registry_repository.py`
- `infrastructure/mysql/process_reminder_anomaly_source.py`
- `infrastructure/mysql/beclass_import_review_anomaly_source.py`
- `infrastructure/mysql/current_anomaly_issue_repository.py`
- `subsystems/anomalies/outbox_worker.py`
- `subsystems/anomalies/ports.py`
- `subsystems/anomalies/government_return_outbound_overage_anomaly_source.py`

## Verification
- layout_status: `custom_current`
- layout_basis: Existing outbox composition regression keeps its original entrypoint; new owner tests use the canonical module root.
- integration_root: `tests/test_subsidy_advance_worker_wiring.py`
- Worker 接線回歸（L23–54，monkeypatch）：其餘已接線的 consumer 結果仍被聚合，測試連線會關閉；測試替身若被要求建立已退役的逐案補助復原 repository 會直接失敗。此斷言不代表已驗證真實資料庫或所有 owner reader。
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/current-issue-runtime-composition/`
