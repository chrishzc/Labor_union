# Domain: anomalies

## Responsibility
擁有 anomaly definition／projection／alert 與人工處理 routing；不擁有被觀測業務 root，也不能以 tracking status 代替 owner completion predicate。

## Subsystems
- `anomalies` — anomaly query/projection/remediation dispatch workers; path: `subsystems/anomalies/index.md`

## External relationships
- depends_on: `orders | scheduling | client-finance | staff-payables | finance-import | government-subsidy | case-import | external-integration/line` — projections/rechecks use owning typed current facts；`LINE-004` consumes LINE Identity current-fact readback。
- depends_on: `external-integration/access` — central worker消費已提交的Access security-alert intent；Access delivery state仍由Access擁有。

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — Anomalies Domain contract
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` — current anomaly amendments/spec-gap status
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/anomalies/`
- integration_root: `tests/domains/anomalies/subsystems/anomalies/integration/` (`layout_gap`: no separate Domain-level integration root observed)
