# Subsystem: orders

## Parent
- domain: `orders`

## Responsibility
將 Orders root facts 組成 read-only Query、zero-write Preview 與 fresh-lock Apply；負責 workflow composition，不重複定義 Domain rules。

## Modules
- `order-tracker-presentation` — Orders tracker主清單與retry的business-facing presentation；path: `modules/order-tracker-presentation.md`
- `historical-adoption` — 既有 Order 的 historical workbook adoption／replay; path: `modules/historical-adoption.md`
- `historical-service-accounting` — 歷史逐月嫂服務天數、單薪帳務與跨 owner Q/P/A; path: `modules/historical-service-accounting.md`
- `historical-precision-restart` — 歷史未服務／服務中案件撤銷 current 服務根並回到正常訂單成立的單交易 Q/P/A; path: `modules/historical-precision-restart.md`
- `historical-adoption-presentation` — historical workbook typed API client／adapter 與狀態統計呈現; path: `modules/historical-adoption-presentation.md`
- `historical-stage-baseline` — 已採納歷史訂單的唯讀作業階段 baseline overlay; path: `modules/historical-stage-baseline.md`
- `actual-start` — Actual Start 正式服務日重建與跨 owner projection；path: `modules/actual-start.md`
- `operational-stage-projection` — Orders 七階段唯讀投影；path: `modules/operational-stage-projection.md`
- `lifecycle-authoritative-facts` — lifecycle／自動完成所需的鎖定根事實；path: `modules/lifecycle-authoritative-facts.md`
- `historical-completion` — Orders-owned Step 11 cross-owner Query、typed referral及fresh settlement Preview／Apply; path: `modules/historical-completion.md`
- `historical-baseline-presentation` — Historical Operational Baseline唯讀Query的business-first presentation; path: `modules/historical-baseline-presentation.md`
- `historical-review-remediation-presentation` — 歷史訂單review更正的business-first呈現與技術詳情分層; path: `modules/historical-review-remediation-presentation.md`
- `order-card-projection` — Orders 管理端案件投影的 typed adaptation 與營運／技術資訊層級; path: `modules/order-card-projection.md`
- `service-completion-presentation` — Orders服務完成Preview／Confirm／Apply與closed business presentation; path: `modules/service-completion-presentation.md`
- `cancellation` — 訂單取消的跨 owner Preview／Apply 與 fresh readback；path: `modules/cancellation.md`
- `terminal-closure-handoff` — terminal lifecycle event／receipt／outbox 的 LINE Identity typed handoff；path: `modules/terminal-closure-handoff.md`
- `order-information` — typed order-information Query／Preview 與既有管理端 readback；path: `modules/order-information.md`
- `order-information` — 服務人員訂單資訊-1／2 typed exact-target Query／Preview；path: `modules/order-information.md`

## Dependencies
- outbound: `scheduling` — 服務日期／assignment 相關跨域協調只透過明確 contract。
- outbound: `anomalies` — owner result 可由 committed outbox 投影為 review/alert，不讓 Anomalies 改 Orders root。

## Contracts
- `domains/orders/` — Orders business rules
- `subsystems/orders/` — Orders workflows／queries
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — outer UoW／receipt-outbox

## Verification routing
- default_boundary: Subsystem
- layout_status: `custom_current`
- test_root: `tests/domains/orders/subsystems/orders/`
- integration_root: `tests/domains/orders/subsystems/orders/integration/`
- integration_root: `ui_react/src/tests/orders_service_dates_flow.test.tsx`
- fixtures_root: `tests/fixtures/`
