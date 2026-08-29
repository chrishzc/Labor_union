# Subsystem: client-finance

## Parent
- domain: `client-finance`

## Responsibility
編排 Client Finance Query／Preview／Apply、退款／沖正與 owner receipts；repository/adapters 不取得 commit ownership。

## Dependencies
- inbound: `finance-import` — 只接受 typed owner delegation。

## Contracts
- `domains/client_finance/` — Client Finance rules
- `subsystems/client_finance/` — Client Finance workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outer UoW

## Verification routing
- default_boundary: Subsystem
- test_root: unknown (`layout_gap`; current tests remain mixed under `tests/`).
