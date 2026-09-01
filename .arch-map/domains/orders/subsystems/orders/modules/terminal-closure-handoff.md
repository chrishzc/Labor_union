# Module: terminal-closure-handoff

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
在既有 Orders lifecycle event／receipt／outbox 的單一 outer UoW 內，於 terminal status 形成不可變 `case_terminal_closure` JSON handoff。此 Module 只保存 Orders source identity、source subject、producer reference、occurred time、correlation 與 idempotency；LINE consumer 不在此寫入。

## Implementation
- `infrastructure/mysql/order_cancellation_repository.py`
- `infrastructure/mysql/order_auto_completion_repository.py`
- `infrastructure/mysql/orders_terminal_closure_source.py` — read-only source adapter for LINE consumption.

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.3.2
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9.5

## Verification
- LINE consumer and handoff oracle remain at tests/domains/external-integration/subsystems/line/modules/line-identity-management/contract/test_terminal_closure_restore.py.
- No schema or release-chain change is part of this Module.
