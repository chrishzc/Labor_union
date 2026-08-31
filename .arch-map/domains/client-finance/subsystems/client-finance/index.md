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

## Modules
- `historical-payment-settlement` — adopted pre-system historical Client payment evidence and exact obligation settlement overlay; path: `modules/historical-payment-settlement.md`
- `historical-payment-settlement-presentation` — owner-page historical Client payment Q/P/A and fresh readback; path: `modules/historical-payment-settlement-presentation.md`
- `over-refund-recovery-presentation` — 客戶退款超額追償的既有安全 workflow 與 business-first React projection; path: `modules/over-refund-recovery-presentation.md`
- `settlement-remediation-presentation` — 客戶應收、退款與補助退還三碼Q/P/A的business-first React projection; path: `modules/settlement-remediation-presentation.md`

## Verification routing
- default_boundary: Subsystem
- current owner-local integration coverage remains catalogued in `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`.
- material module tests use the exact canonical root declared by their module leaf.
