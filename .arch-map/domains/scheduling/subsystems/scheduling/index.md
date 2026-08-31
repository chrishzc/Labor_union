# Subsystem: scheduling

## Parent
- domain: `scheduling`

## Responsibility
將 Scheduling、matching、leave/substitution facts 組成 typed Query／Preview／Apply，維持 fresh owner facts、lock order、idempotency 與 cross-domain coordination。

## Modules
- `matching-coordination` — 候選／決策／plan/package coordination; path: `modules/matching-coordination.md`
- `matching-schedule-confirmation` — current 日期版本的 recipient snapshot／LINE delivery intent／postback readback／正式排班 gate; path: `modules/matching-schedule-confirmation.md`
- `leave-substitution` — 請假／代班 Query／Preview／Apply 與 committed Staff Payables readback; path: `modules/leave-substitution.md`
- `service-before-replacement` — 正式服務前 successor/replacement workflow; path: `modules/service-before-replacement.md`
- `current-anomaly-facts` — `SCHEDULE-002/003/006` typed zero-write current-fact readback; path: `modules/current-anomaly-facts.md`

## Dependencies
- outbound: `orders` — order/case lifecycle boundary。
- outbound: `anomalies` — 只輸出 owner evidence/projection，不讓 anomaly status 取代 owner facts。

## Contracts
- `domains/scheduling/` — Scheduling domain rules
- `subsystems/scheduling/` — Scheduling workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outer UoW／typed errors

## Verification routing
- default_boundary: Subsystem
- test_root: unknown (`layout_gap`; focused tests currently live under flat `tests/`)
- integration_root: `tests/integration/`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.
