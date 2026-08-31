# Subsystem: orders

## Parent
- domain: `orders`

## Responsibility
將 Orders root facts 組成 read-only Query、zero-write Preview 與 fresh-lock Apply；負責 workflow composition，不重複定義 Domain rules。

## Modules
- `order-tracker-presentation` — Orders tracker主清單與retry的business-facing presentation；path: `modules/order-tracker-presentation.md`
- `historical-adoption` — 既有 Order 的 historical workbook adoption／replay; path: `modules/historical-adoption.md`
- `actual-start` — Actual Start 正式服務日重建與跨 owner projection；path: `modules/actual-start.md`
- `operational-stage-projection` — Orders 七階段唯讀投影；path: `modules/operational-stage-projection.md`
- `lifecycle-authoritative-facts` — lifecycle／自動完成所需的鎖定根事實；path: `modules/lifecycle-authoritative-facts.md`
- `historical-completion` — Orders-owned Step 11 cross-owner read-only composition、typed referral與React projection; path: `modules/historical-completion.md`
- `historical-baseline-presentation` — Historical Operational Baseline唯讀Query的business-first presentation; path: `modules/historical-baseline-presentation.md`
- `historical-review-remediation-presentation` — 歷史訂單review更正的business-first呈現與技術詳情分層; path: `modules/historical-review-remediation-presentation.md`
- `order-card-projection` — Orders 管理端案件投影的 typed adaptation 與營運／技術資訊層級; path: `modules/order-card-projection.md`
- `service-completion-presentation` — Orders服務完成Preview／Confirm／Apply與closed business presentation; path: `modules/service-completion-presentation.md`

## Dependencies
- outbound: `scheduling` — 服務日期／assignment 相關跨域協調只透過明確 contract。
- outbound: `anomalies` — owner result 可由 committed outbox 投影為 review/alert，不讓 Anomalies 改 Orders root。

## Contracts
- `domains/orders/` — Orders business rules
- `subsystems/orders/` — Orders workflows／queries
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outer UoW／receipt-outbox

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/orders/subsystems/orders/`
- integration_root: `tests/domains/orders/subsystems/orders/integration/`
- fixtures_root: `tests/fixtures/`
