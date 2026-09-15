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
- `deposit-skip` — 一般市民由管理員允許訂金未付仍推進，不變更應收與核銷狀態；path: `modules/deposit-skip.md`
- `receipt-reconciliation` — 客戶銀行收款的精確核銷、明示超收處理與 owner Preview／Apply；path: `modules/receipt-reconciliation.md`
- `obligation-planning` — plans canonical Client Finance stage obligations, including date-only replacement without customer cash impact; path: `modules/obligation-planning.md`
- `historical-payment-settlement` — adopted pre-system historical Client payment evidence and exact obligation settlement overlay; path: `modules/historical-payment-settlement.md`
- `historical-service-accounting` — 歷史服務天數驅動的客戶應收、退款／補收差額; path: `modules/historical-service-accounting.md`
- `historical-payment-settlement-presentation` — owner-page historical Client payment Q/P/A and fresh readback; path: `modules/historical-payment-settlement-presentation.md`
- `over-refund-recovery-presentation` — 客戶退款超額追償的既有安全 workflow 與 business-first React projection; path: `modules/over-refund-recovery-presentation.md`
- `settlement-remediation-presentation` — 客戶應收、退款與補助退還三碼Q/P/A的business-first React projection; path: `modules/settlement-remediation-presentation.md`
- `payment-destination-configuration` — 工會／代收付帳戶的版本化 Q/P/A 與客戶契約 typed projection; path: `modules/payment-destination-configuration.md`
- `legacy-virtual-account-import` — 舊流程案件／虛擬帳號對照的 XLSX Preview／Apply 與多案命中人工核銷邊界; path: `modules/legacy-virtual-account-import.md`

## Verification routing
- default_boundary: Subsystem
- layout_status: `custom_current`
- layout_basis: FinancePage spans multiple Client Finance modules, so its frontend composition tests use the mirrored subsystem integration root.
- integration_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/integration/`
- current owner-local integration coverage remains catalogued in `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`.
- material module tests use the exact canonical root declared by their module leaf.
