# Module: lifecycle-authoritative-facts

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
鎖定並組成 Orders lifecycle／自動完成的 authoritative facts，包含有效正式服務日、actual end 與 completion instant；缺少完整 service-time tuple 時，依 Orders contract 以最後正式服務日的台北日終完成。

## Implementation
- primary:
  - `subsystems/orders/lifecycle_authoritative_facts_loader.py`
  - `subsystems/orders/lifecycle_authoritative_facts.py`
  - `subsystems/orders/auto_completion_workflow.py`

## Dependencies
- outbound: `scheduling/scheduling` — 有效 generation、正式 assignment 與 official service dates。
- outbound: `client-finance/client-finance` — deposit settlement root fact。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — lifecycle completion instant semantics。

## Provenance
- Lock-held facts and auto-completion workflow — `source_observed` — `subsystems/orders/lifecycle_authoritative_facts_loader.py`.

## Change triggers
Reconcile when lifecycle root facts, completion instant, effective scheduling readback, or auto-completion blocker semantics change.
