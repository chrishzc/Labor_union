# Subsystem: anomalies

## Parent
- domain: `anomalies`

## Responsibility
組合 current-only issue query/detail、owner-fact detector、projection reconciliation 與 durable recheck consumer；owner root mutation 必須回 owning Subsystem。

## Modules
- `current-issue-presentation` — 15-code current-only清單／detail的business-first React projection; path: `modules/current-issue-presentation.md`
- `finance-correction-presentation` — Finance Import 更正的既有安全 readback 與 closed 業務錯誤投影; path: `modules/finance-correction-presentation.md`
- `anomaly-detail-presentation` — 異常詳情、處理方式與排班導向的業務資訊層級; path: `modules/anomaly-detail-presentation.md`
- `line-notification-current-issue` — LINE-006 typed owner predicate consumer與fail-closed reconcile；path: `modules/line-notification-current-issue.md`
- `scheduling-current-issue` — `SCHEDULE-002/003/006` typed owner predicate consumers；path: `modules/scheduling-current-issue.md`
- `government-subsidy-current-issue` — `GOVSUB-001/002/004` typed owner predicate consumers；path: `modules/government-subsidy-current-issue.md`
- `case-pairing-current-issue` — `BECLASS-001/IMPORT-003` typed owner predicate consumers；path: `modules/case-pairing-current-issue.md`
- `payroll-current-issue` — `PAYOUT-002` typed Payroll owner predicate consumer；path: `modules/payroll-current-issue.md`

## Dependencies
- outbound: owning subsystems — Query/Preview/Apply delegation and fresh predicate recheck。
- outbound: `external-integration/line` — `LINE-004`只消費 typed role-scoped identity current-fact readback；合法 customer+staff 雙角色不投影為異常。
- outbound: `external-integration/line` — `LINE-006`只消費 typed notification-failure current-fact readback；不查LINE tables或重算delivery／applicability。
- outbound: `external-integration/access` — `outbox_worker.py`消費已提交的Access alert intent並注入projection sink。
- inbound: `external-integration/access` — 只透過`SecurityAlertSink` protocol接受投影payload，不讓Access依賴Anomalies concrete implementation。

## Contracts
- `domains/anomalies/` — Anomaly definitions/rules
- `subsystems/anomalies/` — projection/workers/remediation routing
- `subsystems/anomalies/line_identity_current_issue_consumer.py` — LINE-004 role-scoped current predicate；只產生 closed subject／redacted details，沒有 Anomalies-owned repair action
- `infrastructure/mysql/line_identity_current_issue_adapter.py` — 將 LINE repository typed readback組成 complete `OwnerSnapshot`，不直接查 LINE private tables
- `subsystems/anomalies/line_notification_current_issue_consumer.py`與`infrastructure/mysql/line_notification_current_issue_adapter.py` — LINE-006 public identity不變的typed predicate consumer／adapter。
- `domains/anomalies/current_issue.py` — closed current issue identity、opaque issue key與recheck scope
- `api/routes/anomaly_registry.py::GET /api/v1/anomalies/{issue_key}` — canonical current detail；同一路徑對 legacy 64-hex identity回 typed 410
- `subsystems/anomalies/system_alert_projection.py` — Anomalies-owned `system_alerts` projection implementation；helper不擁有commit
- `subsystems/anomalies/outbox_worker.py` — central composition root，將`upsert_system_alert`注入Access consumer
- `subsystems/access/security_alert_outbox.py::SecurityAlertSink` — caller-composed projection port
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outbox/durable job contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/anomalies/subsystems/anomalies/`
- integration_root: `tests/domains/anomalies/subsystems/anomalies/integration/`
- higher_boundary: `tests/test_system_alert_service.py`、`tests/test_system_alert_current_projection_schema.py`與Access integration root。
- cross_domain: `tests/domains/anomalies/subsystems/anomalies/integration/test_line_identity_current_issue_consumer.py`；LINE Identity first-release living baseline由Global schema/release routing分類。
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/index.md`.
