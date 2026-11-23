# Domain: anomalies

## Responsibility
擁有 anomaly definition／projection／alert 與人工處理 routing；不擁有被觀測業務 root，也不能以 tracking status 代替 owner completion predicate。

## Subsystems
- `anomalies` — anomaly query/projection/remediation dispatch workers; path: `subsystems/anomalies/index.md`

## External relationships
- depends_on: `external-integration/line` — the sole current anomaly projection consumes LINE-006 notification-failure typed current-fact readback；other owner facts remain owner-local validation/evidence and do not form runtime anomaly products。
- depends_on: `external-integration/access` — central worker消費已提交的Access security-alert intent；Access delivery state仍由Access擁有。

## Contracts
- `.arch-map/requirements/06_Anomalies_Domain.md` — Anomalies Domain contract
- `.arch-map/requirements/15_正式規格索引與裁決總表.md` — current anomaly amendments/spec-gap status
- `.arch-map/requirements/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- layout_status: `custom_current`
- default_boundary: Domain
- test_root: `tests/domains/anomalies/`
