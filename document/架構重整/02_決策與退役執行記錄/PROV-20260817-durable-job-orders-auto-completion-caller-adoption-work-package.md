---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-durable-job-orders-auto-completion-caller-adoption
date: 2026-08-17
owner: Orders
domain: Orders
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS
approval_required: 核准此 exact Orders Auto Completion Durable Job Caller Adoption Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Orders Auto Completion durable caller adoption工作包

只把`orders_auto_completion_apply` dispatcher切到Core／bridge；不改Orders lifecycle eligibility、worker、public route、
React或DB。

## Exact write set

- `subsystems/orders/auto_completion_job_dispatch.py`
- `tests/test_order_auto_completion_job_dispatch.py`
- `tests/test_order_auto_completion_durable_worker_e2e.py`
- `tests/test_order_auto_completion_disposable_mysql_e2e.py`
- `document/架構重整/01_規格基線/01_Orders_Domain.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-orders-auto-completion-caller-adoption/`（new）。

## Acceptance

- dispatcher不得吞idempotency conflict；same-key不同payload/actor/version fail closed並可觀測。
- enqueue使用bridge、outer UoW與Core equality；0 hidden commit；accepted不冒充order completed。
- crash/retry/rollback disposable MySQL evidence、0 provider、0 schema、0 React。

DB：Scope BLOCKED待核准；Change inventory PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
