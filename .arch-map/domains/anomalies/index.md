# Domain: anomalies

## Responsibility
擁有 anomaly definition／projection／alert 與人工處理 routing；不擁有被觀測業務 root，也不能以 tracking status 代替 owner completion predicate。

## Subsystems
- `anomalies` — anomaly query/projection/remediation dispatch workers; path: `subsystems/anomalies/index.md`

## External relationships
- depends_on: `orders | scheduling | client-finance | staff-payables | finance-import | government-subsidy | case-import` — projections/rechecks use owning facts。

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — Anomalies Domain contract
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` — current anomaly amendments/spec-gap status
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: unknown (`layout_gap`; no `tests/domains/anomalies/` observed)
- integration_root: unknown; resolve scoped from current `tests/`.
