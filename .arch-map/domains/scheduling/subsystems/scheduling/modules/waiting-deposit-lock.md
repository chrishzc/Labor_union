# Module: waiting-deposit-lock

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
擁有 waiting-deposit 檔期鎖的取得、釋放與訂單取消時的原子收斂；只解除 Scheduling-owned 占用，不自行推進 Orders lifecycle。

## Implementation
- primary:
  - `domains/scheduling/waiting_deposit_lock.py`
  - `subsystems/scheduling/availability_lock_acquisition_workflow.py`
  - `subsystems/scheduling/availability_lock_release_workflow.py`
  - `subsystems/scheduling/availability_lock_cancellation_workflow.py`
- entrypoints:
  - `api/routes/caregiver_availability_locks.py`

## Dependencies
- outbound: `orders/orders` — 訂單取消由 Orders outer Unit of Work 傳入已鎖定 lifecycle command envelope。
- inbound: `scheduling/matching-coordination` — matching plan 與 commitment 提供檔期鎖候選事實。

## Contracts
- Waiting-deposit lock ownership and cancellation — `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`.
- Cancellation must remove future Scheduling occupancy — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.5.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/waiting-deposit-lock/`.
- higher_boundary: 跨 Orders、Scheduling、Client Finance、Payroll 的 disposable-MySQL 取消交易依 Global Test Map 的 higher-boundary exception 路由。
- routing: `.arch-map/tests/index.md` and `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Scheduling ownership and Orders cancellation dependency — `architecture_declared` — current Orders/Scheduling specs.
- Workflow and route paths — `source_observed` — current repository source.
- Cross-owner disposable MySQL verification — `source_observed` — current Global Test Map higher-boundary exception.

## Change triggers
Reconcile when lock lifecycle、matching-plan eligibility、Orders cancellation integration、occupancy mutex、entrypoint or verification routing changes.
