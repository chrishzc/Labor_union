# Module: schedule-generation

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
從 current Scheduling generation facts 產生版本化 assignment／buffer candidate。Orders Terms caller 必須先比對 candidate 與 current effective assignment 的 identity／人員／日期／區間形狀；形狀未變時 candidate 只供 Finance／Payroll 計算與真實 assignment identity mapping，不得持久化新 generation。尚無 assignment／buffer 時，開始日／服務天數 candidate 不虛構 segment；已有服務日期或排班事實時仍 fail closed，分別要求替換日期或正式重新分配。

## Implementation
- primary:
  - `domains/scheduling/generation.py`
  - `domains/scheduling/assignment_plan.py`
  - `domains/scheduling/bootstrap.py`
  - `api/schemas/assignment_plan.py`

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
