# Domain: finance-import

## Responsibility
擁有銀行流水來源事實、解析／分類與 reconciliation evidence；正式會計狀態由對應 owning Domain mutation。

## Subsystems
- `finance-import` — bank import Query／Preview／Apply 與 owner delegation; path: `subsystems/finance-import/index.md`

## External relationships
- depends_on: `client-finance` — client-side settlement delegation。
- depends_on: `staff-payables` — staff-side settlement delegation。
- depends_on: `government-subsidy` — subsidy bank allocation/reversal delegation when applicable。
- outbound: `anomalies` — unresolved classification may create projection/evidence, not owner state。

## Contracts
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md` — Finance Import canonical Domain contract
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` — current bank/anomaly processing contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: unknown (`layout_gap`; current finance/import tests are under `tests/imports/` and flat `tests/`)
- integration_root: `tests/imports/` (legacy functional root); see Test Map.
