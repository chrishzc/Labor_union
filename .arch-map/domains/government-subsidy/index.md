# Domain: government-subsidy

## Responsibility
擁有政府補助申請、核准、撥款、allocation 與 reversal roots，以及與帳務對接時的 owner invariants。

## Subsystems
- `government-subsidy` — Subsidy lifecycle/query/apply workflows; path: `subsystems/government-subsidy/index.md`

## External relationships
- depended_by: `finance-import` — bank evidence may be classified/delegated into subsidy owner flow。

## Contracts
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md` — Government Subsidy canonical Domain contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/government-subsidy/`
- subsystem_root: tests/domains/government-subsidy/subsystems/government-subsidy/
- anomaly projections sourced from subsidy facts remain under the Anomalies test owner.
- routing: `.arch-map/tests/domains/government-subsidy/index.md`.
