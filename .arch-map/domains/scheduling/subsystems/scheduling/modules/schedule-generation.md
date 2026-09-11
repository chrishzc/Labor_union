# Module: schedule-generation

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
從 current Scheduling generation facts 產生版本化 assignment／buffer candidate，並在未指派時將 Orders Terms 影響表示為不虛構 segment 的空 generation。服務天數改變仍 fail closed，需由正式排班重新分配。

## Implementation
- primary:
  - `domains/scheduling/generation.py`

## Dependencies
- inbound: `orders/order-terms` — Orders Terms workflow 只透過 typed generation candidate 交付排班影響。
- inbound: Scheduling workflows — 使用 current generation facts 建立正式重建 candidate。

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — generation、assignment 與 occupancy ownership。

## Verification
- default_boundary: Module
- cross-owner behavior is verified by the Orders Terms owner at its declared focused test root.

## Provenance
- Scheduling generation ownership — `architecture_declared` — Scheduling formal spec.
- Candidate builders and cross-owner preassignment behavior — `source_observed` — current source and focused Orders integration test.

## Change triggers
Reconcile when generation versioning, assignment／buffer candidate, preassignment fail-closed rules, or callers change.
