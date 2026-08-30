# Subsystem: anomalies

## Parent
- domain: `anomalies`

## Responsibility
組合 current-only issue query/detail、owner-fact detector、projection reconciliation 與 durable recheck consumer；owner root mutation 必須回 owning Subsystem。

## Dependencies
- outbound: owning subsystems — Query/Preview/Apply delegation and fresh predicate recheck。
- outbound: `external-integration/line` — `LINE-004`只消費 typed identity current-fact readback；合法 customer+staff 雙角色與單列 root schema 限制不投影為異常。
- outbound: `external-integration/access` — `outbox_worker.py`消費已提交的Access alert intent並注入projection sink。
- inbound: `external-integration/access` — 只透過`SecurityAlertSink` protocol接受投影payload，不讓Access依賴Anomalies concrete implementation。

## Contracts
- `domains/anomalies/` — Anomaly definitions/rules
- `subsystems/anomalies/` — projection/workers/remediation routing
- `subsystems/anomalies/line_identity_current_issue_consumer.py` — LINE-004 role-scoped current predicate；只產生 closed subject／redacted details，沒有 Anomalies-owned repair action
- `infrastructure/mysql/line_identity_current_issue_adapter.py` — 將 LINE repository typed readback組成 complete `OwnerSnapshot`，不直接查 LINE private tables
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
- cross_domain: `tests/domains/anomalies/subsystems/anomalies/integration/test_line_identity_current_issue_consumer.py`與`tests/test_line_identity_management_first_release.py`。
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/index.md`.
