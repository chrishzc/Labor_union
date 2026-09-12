# Module: receipt-reconciliation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由 Client Finance 驗證客戶收款與應收義務，編排 fresh Preview／Apply、核銷分配與收據。需人工核對的金額差異必須在正式帳務寫入前拒絕；明示超收處理沿既有退款義務流程。

## Implementation
- primary:
  - `domains/client_finance/reconciliation.py`
  - `subsystems/client_finance/reconciliation_workflow.py`
  - `infrastructure/mysql/client_receipt_reconciliation_repository.py`
- entrypoints:
  - `api/routes/client_receipt_reconciliation.py`

## Dependencies
- inbound: `finance-import` — 透過 owning-domain composite 委派收款核銷並保留外層交易。
- outbound: `orders` — 以已提交的 deposit intent 通知訂金核銷結果。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 精確分配、超收處理及穩定錯誤。
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md` — owner delegation 與零部分帳務寫入。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_receipt_overage.py`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`

## Provenance
- Owner 與金額核銷規則 — `architecture_declared` — Client Finance 正式規格。
- Workflow、repository 與既有測試位置 — `source_observed` — 上述 current implementation 與 test。

## Change triggers
核銷 eligibility、receipt identity、owner delegation、transaction owner 或驗證位置改變時重新核對。
