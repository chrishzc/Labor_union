# Module: assignment-terms-impact

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
保存 assignment 建立／替換時的 immutable Payroll rate snapshot，並套用正式 Payroll terms impact。Actual Start 日期 replacement 只可把唯一 source assignment frozen snapshot 原值搬移到 successor，不改 Payroll root、obligation 或金額，且缺少 source snapshot 時不得 fallback；歷史重啟首次建立安排沒有 source snapshot 時，才可使用案件既有 case policy。任何分支都不得自行產生費率。

## Implementation
- primary:
  - `subsystems/payroll/terms_impact.py`
  - `infrastructure/mysql/payroll_terms_writer.py`

## Dependencies
- inbound: `orders/orders/module:service-date-confirmation` — confirmed-date 保存不再建立 assignment 或 rate；Precision Restart 後由明確正式安排操作在同一 outer transaction 凍結 rate。
- inbound: `orders/orders/module:order-actual-start` — 日期 replacement 建立 successor assignment 時，只搬移唯一 source snapshot，不形成 Payroll root impact。
- inbound: `orders/orders/module:order-terms` — 將 Orders 的工時與費用轉為 Payroll typed impact candidate；浮點 HTTP 值在此邊界正規化為精確 Decimal。
- outbound: `scheduling` — 只消費 canonical assignment identity resolution。

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/assignment-terms-impact/`

## Provenance
- Assignment-owned rate snapshots 由 Payroll writer 保存 — `source_observed` — `infrastructure/mysql/payroll_terms_writer.py`。
- Payroll Terms impact candidate 與 Orders-to-Payroll typed conversion 由 Payroll workflow 保存 — `source_observed` — `subsystems/payroll/terms_impact.py`。
- Restart-specific current assignment 必須可被 ordinary Actual Start read model 消費 — `requirement_declared` — current task acceptance 與 `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。
- Actual Start successor snapshot carry-forward 不改 Payroll root — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4、`03_Payroll_Domain.md`。

## Change triggers
Reconcile when assignment rate carry-forward、case-policy fallback、Payroll versioning or assignment identity resolution changes.
