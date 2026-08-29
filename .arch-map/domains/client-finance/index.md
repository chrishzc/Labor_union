# Domain: client-finance

## Responsibility
擁有客戶應收、收款、退款、沖正、調整與核銷根事實；銀行匯入只能委派，不可直接改 owner state。

## Subsystems
- `client-finance` — Client Finance typed workflows／queries; path: `subsystems/client-finance/index.md`

## External relationships
- depended_by: `finance-import` — bank facts/classification may delegate Client Finance commands。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — Client Finance canonical contract
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — refund/payables executable boundary
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: unknown (`layout_gap`; no `tests/domains/client_finance/` observed)
- integration_root: unknown; resolve scoped from current `tests/`.
