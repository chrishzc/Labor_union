# Subsystem: government-subsidy

## Parent
- domain: `government-subsidy`

## Responsibility
編排 subsidy Query／Preview／Apply、allocation/reversal 與 owner receipts，拒絕由 generic finance importer 直接改寫 domain roots。

## Dependencies
- inbound: `finance-import` — typed owner delegation only。

## Contracts
- `domains/government_subsidy/` — Subsidy rules
- `subsystems/government_subsidy/` — Subsidy workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Verification routing
- default_boundary: Subsystem
- test_root: unknown (`layout_gap`; current tests remain mixed under `tests/`).
