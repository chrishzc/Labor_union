# Module: lifecycle-authoritative-facts

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
鎖定並組成 Orders lifecycle／自動完成的 authoritative facts，包含有效正式服務日、actual end 與 completion instant；缺少完整 service-time tuple 時，依 Orders contract 以最後正式服務日的台北日終完成。

## Implementation
- primary:
  - `subsystems/orders/service_start_lifecycle.py` — 已正式排班案件至約定開工日才轉為服務中；不重排班或寄新通知。
  - `infrastructure/mysql/service_start_lifecycle_repository.py` — 共用 occupancy mutex／fresh owner facts 與 canonical lifecycle writer；AutoComplete 保留唯一完工權。
  - `domains/orders/lifecycle.py`
  - `infrastructure/mysql/order_auto_completion_repository.py` — 完工同交易同步補助應退、月嫂應付及 Orders 唯一付款日；無 LINE 外部效果。
  - `subsystems/orders/lifecycle_authoritative_facts_loader.py`
  - `subsystems/orders/lifecycle_authoritative_facts.py`
  - `subsystems/orders/lifecycle_control_read_facts.py`
  - `subsystems/orders/order_lifecycle_command_envelope.py`
  - `subsystems/orders/auto_completion_workflow.py`
  - `api/dependencies/order_auto_completion.py`
  - `api/routes/order_auto_completion.py` — canonical completion commands and readonly automatic-completion status。
  - `api/schemas/order_auto_completion.py`

## Dependencies
- outbound: `scheduling/scheduling` — 有效 generation、正式 assignment 與 official service dates。
- outbound: `client-finance/client-finance` — deposit settlement root fact，以及當前有效的 typed 未付人工放行；後者只解除訂金進度關卡，不改核銷事實。

- outbound: `payroll/payroll-rebuild` — 正式完工後自動同步薪資與付款日。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — lifecycle completion instant semantics。

## Provenance
- Lock-held facts and auto-completion workflow — `source_observed` — `subsystems/orders/lifecycle_authoritative_facts_loader.py`.

## Change triggers
Reconcile when lifecycle root facts, completion instant, effective scheduling readback, or auto-completion blocker semantics change.
