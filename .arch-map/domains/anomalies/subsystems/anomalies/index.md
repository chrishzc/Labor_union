# Subsystem: anomalies

## Parent
- domain: `anomalies`

## Responsibility
組合 current alerts、detail/recovery projections、owner-specific remediation dispatch 與 outbox consumers；owner root mutation 必須回 owning Subsystem。

## Dependencies
- outbound: owning subsystems — Query/Preview/Apply delegation and fresh predicate recheck。

## Contracts
- `domains/anomalies/` — Anomaly definitions/rules
- `subsystems/anomalies/` — projection/workers/remediation routing
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outbox/durable job contract

## Verification routing
- default_boundary: Subsystem
- test_root: unknown (`layout_gap`; current tests remain mixed under flat `tests/` and integration roots).
