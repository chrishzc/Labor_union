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
- test_root: unknown (`layout_gap`; no `tests/domains/payroll/` observed)
- integration_root: `tests/subsystems/payroll/` — current subsystem-owned root.
