# Subsystem: finance-import

## Parent
- domain: `finance-import`

## Responsibility
解析與保存 bank source facts，提供 zero-write preview、fresh apply 與 typed delegation；不得自行寫入 Client Finance／Staff Payables／Subsidy owner roots。

## Dependencies
- outbound: `client-finance | staff-payables | government-subsidy` — typed owner commands。
- outbound: `anomalies` — projection/alert evidence only。

## Contracts
- `domains/finance_import/` — Finance Import rules
- `subsystems/finance_import/` — Finance Import workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — receipt/outbox/idempotency

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/finance-import/subsystems/finance-import/`
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/`.
