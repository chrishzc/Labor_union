# Module: deposit-skip

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
提供僅限一般市民、由 system admin 明確操作的訂金未付放行 Preview／Apply；保存原因與冪等 receipt，維持原訂金條款、應收與未付狀態，並經 Orders writer 真實推進 lifecycle 與作業階段。

## Implementation
- rule: `domains/client_finance/deposit_skip.py`
- workflow: `subsystems/client_finance/deposit_skip_workflow.py`
- adapter: `infrastructure/mysql/client_deposit_skip_repository.py`
- Orders delivery: `subsystems/orders/client_finance_outbox_consumer.py`
- stage projection: `infrastructure/mysql/orders_stage_projection_repository.py`, `subsystems/orders/stage_projection_query.py`, `subsystems/orders/core_stage_projection_query.py`
- composition: `api/dependencies/client_deposit_skip.py`
- api: `api/routes/client_deposit_skip.py`
- presentation: `ui_react/src/components/ClientDepositSkipActions.tsx`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 資格、稽核及不修改訂金事實的放行規則。
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling 只讀取 Client Finance typed settlement。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_deposit_skip.py`
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/deposit-skip/`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`

## Provenance
- Eligibility and manual-entry contract — `human_authorized` — current user clarification.
- Source and verification paths — `source_observed` — current workspace.

## Change triggers
Reconcile when eligibility、audit fields、override invalidation、API entry或focused test roots change。
