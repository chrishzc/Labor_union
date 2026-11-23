# Module: line-notification-current-issue

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
只消費LINE-owned typed LINE-006 current-fact predicate，維持公開subject `case_no + notification_reason`；readback incomplete／unavailable時fail closed，不查LINE tables、不重算Delivery狀態、不寫LINE root。這是目前唯一 runtime anomaly consumer。

## Implementation
- primary:
  - `subsystems/anomalies/line_notification_current_issue_consumer.py`
  - `infrastructure/mysql/line_notification_current_issue_adapter.py`
  - `infrastructure/mysql/anomaly_runtime.py`

## Contracts
- `.arch-map/requirements/06_Anomalies_Domain.md` — LINE-006 public identity與current-only reconcile。
- `subsystems/line/notification_failure_current_fact.py` — LINE owner typed readback。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/line-notification-current-issue/`
- higher_boundary:
  - [公開明細與復原投影整合驗證](../../../../../../tests/domains/anomalies/subsystems/anomalies/integration/test_anomaly_public_detail_recovery_contract.py) 歸屬 [Anomalies Subsystem整合驗證](../index.md#verification-routing)，此處為上位證據引用。
  - 唯讀測試替身（L165–213）：兩個案例只呼叫 `query_current`。復原查詢檢查 `case_no`、`notification_reason` 及來源版本；公開明細案例確認 `LINE-006`，不含 timeline 或 workflow status。這些斷言不涵蓋本 Module 的 consumer、adapter、reconcile 或實際投遞。

## Change triggers
Reconcile when LINE-006 subject identity、typed readback consumer、fail-closed reconcile或runtime composition改變。
