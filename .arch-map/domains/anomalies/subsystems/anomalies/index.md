# Subsystem: anomalies

## Parent
- domain: `anomalies`

## Responsibility
組合 current-only issue query/detail、owner-fact detector、projection reconciliation 與 durable recheck consumer；owner root mutation 必須回 owning Subsystem。

## Modules
- `anomaly-registry` — closed definition、source-bound recovery descriptor與public detail contract；path: `modules/anomaly-registry.md`
- `current-issue-presentation` — LINE-006 current-only清單／detail的business-first React projection; path: `modules/current-issue-presentation.md`
- `anomaly-detail-presentation` — 異常詳情、處理方式與排班導向的業務資訊層級; path: `modules/anomaly-detail-presentation.md`
- `line-notification-current-issue` — LINE-006 typed owner predicate consumer與fail-closed reconcile；path: `modules/line-notification-current-issue.md`
- `current-issue-runtime-composition` — durable recheck runtime的owner reader／consumer組合；path: `modules/current-issue-runtime-composition.md`

## Dependencies
- outbound: `external-integration/line` — LINE-006 Query/readback/recheck delegation only；退役碼回各自 owner validation／migration boundary。
- outbound: `external-integration/line` — `LINE-006`只消費 typed notification-failure current-fact readback；不查LINE tables或重算delivery／applicability。
- outbound: `external-integration/access` — `outbox_worker.py`消費已提交的Access alert intent並注入projection sink。
- inbound: `external-integration/access` — 只透過`SecurityAlertSink` protocol接受投影payload，不讓Access依賴Anomalies concrete implementation。

## Contracts
- `domains/anomalies/` — Anomaly definitions/rules
- `subsystems/anomalies/` — projection/workers/remediation routing
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
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/index.md`.
