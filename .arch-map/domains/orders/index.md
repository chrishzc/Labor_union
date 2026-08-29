# Domain: orders

## Responsibility
擁有訂單條款、服務開始／完成、取消、reopen 與 lifecycle 根事實；不把 UI、API 或 persistence 形狀當成業務 Authority.

## Subsystems
- `orders` — 編排 Orders Query／Preview／Apply、read models 與 owner outbox; path: `subsystems/orders/index.md`

## External relationships
- depended_by: `scheduling` — 排班／服務協調需要既有 order/case lifecycle。
- depended_by: `case-import` — formal case bootstrap 最終必須進入 Orders-owned lifecycle。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders canonical Domain contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation／transaction contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/orders/`
- integration_root: `tests/integration/` — shared legacy higher-boundary root; see `.arch-map/tests/domains/orders/index.md`.
