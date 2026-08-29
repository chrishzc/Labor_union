# Domain: staff-payables

## Responsibility
擁有月嫂應付、出款、退匯／沖正及對應 settlement lifecycle，不由 Payroll 或銀行匯入直接改寫。

## Subsystems
- `staff-payables` — Staff Payables query/apply/export workflows; path: `subsystems/staff-payables/index.md`

## External relationships
- depended_by: `finance-import` — bank facts may delegate payables owner commands。

## Contracts
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md` — Staff Payables Domain contract
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — payables/refund executable boundary
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/staff-payables/`
- subsystem_root: `tests/domains/staff-payables/subsystems/staff-payables/`
- higher_boundary: shared acceptance/disposable-MySQL suites remain under their current higher roots.
- routing: `.arch-map/tests/domains/staff-payables/index.md`.
