# Domain: payroll

## Responsibility
擁有由正式 assignment/service facts 導出的薪資義務、調整與 payroll lifecycle；不擁有 assignment 本身。

## Subsystems
- `payroll` — Payroll query/preview/apply 與重建／調整 workflow; path: `subsystems/payroll/index.md`

## External relationships
- depends_on: `scheduling` — assignment/service ownership 是 payroll 的上游根事實。

## Contracts
- `document/架構重整/01_規格基線/03_Payroll_Domain.md` — Payroll canonical Domain contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/payroll/`
- subsystem_root: tests/domains/payroll/subsystems/payroll/
- higher_boundary: shared cross-domain/disposable-MySQL/Task 97 suites remain at their owning higher roots.
- routing: `.arch-map/tests/domains/payroll/index.md`.
