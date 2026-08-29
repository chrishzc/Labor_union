# Subsystem: orders

## Parent
- domain: `orders`

## Responsibility
將 Orders root facts 組成 read-only Query、zero-write Preview 與 fresh-lock Apply；負責 workflow composition，不重複定義 Domain rules。

## Modules
- `historical-adoption` — 既有 Order 的 historical workbook adoption／replay; path: `modules/historical-adoption.md`

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
