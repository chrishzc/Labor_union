# Module: assignment-terms-impact

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
保存 assignment 建立／替換時的 immutable Payroll rate snapshot，並套用正式 Payroll terms impact；rate 必須沿 source assignment frozen policy，沒有 source snapshot 時才使用案件既有 case policy，不得自行產生費率。

## Implementation
- primary:
  - `infrastructure/mysql/payroll_terms_writer.py`

## Dependencies
- inbound: `orders/orders/module:service-date-confirmation` — Precision Restart 後建立 canonical assignment 時，同一 outer transaction 凍結 rate。
- outbound: `scheduling` — 只消費 canonical assignment identity resolution。

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/assignment-terms-impact/`

## Provenance
- Assignment-owned rate snapshots 由 Payroll writer 保存 — `source_observed` — `infrastructure/mysql/payroll_terms_writer.py`。
- Restart-specific current assignment 必須可被 ordinary Actual Start read model 消費 — `requirement_declared` — current task acceptance 與 `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。

## Change triggers
Reconcile when assignment rate carry-forward、case-policy fallback、Payroll versioning or assignment identity resolution changes.
