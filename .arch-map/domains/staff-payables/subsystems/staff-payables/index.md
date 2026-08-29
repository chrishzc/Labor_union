# Subsystem: staff-payables

## Parent
- domain: `staff-payables`

## Responsibility
編排 staff payable owner Query／Preview／Apply、export/read models 與 settlement transitions；不從 imported bank row 重建 owner state。

## Dependencies
- inbound: `finance-import` — typed bank classification/delegation only。

## Contracts
- `domains/staff_payables/` — Staff Payables rules
- `subsystems/staff_payables/` — Staff Payables workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Verification routing
- default_boundary: Subsystem
- test_root: unknown (`layout_gap`; current tests remain mixed under `tests/`).
