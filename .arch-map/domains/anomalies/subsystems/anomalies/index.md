# Subsystem: anomalies

## Parent
- domain: `anomalies`

## Responsibility
組合 current alerts、detail/recovery projections、owner-specific remediation dispatch 與 outbox consumers；owner root mutation 必須回 owning Subsystem。

## Dependencies
- outbound: owning subsystems — Query/Preview/Apply delegation and fresh predicate recheck。
- outbound: `external-integration/access` — `outbox_worker.py`消費已提交的Access alert intent並注入projection sink。
- inbound: `external-integration/access` — 只透過`SecurityAlertSink` protocol接受投影payload，不讓Access依賴Anomalies concrete implementation。

## Contracts
- `domains/anomalies/` — Anomaly definitions/rules
- `subsystems/anomalies/` — projection/workers/remediation routing
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
