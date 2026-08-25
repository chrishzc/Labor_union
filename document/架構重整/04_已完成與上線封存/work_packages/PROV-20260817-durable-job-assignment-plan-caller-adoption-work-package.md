---
doc_type: work-package
declared_status: completed
activation_state: completed-local-validated-2026-08-22
authority: user-approved-in-spec-auto-activation-2026-08-22
identity: PROV-20260817-durable-job-assignment-plan-caller-adoption
date: 2026-08-17
owner: Orders / Assignment Plan
domain: Orders / Scheduling
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS
approval_required: 核准此 exact Assignment Plan Durable Job Caller Adoption Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Assignment Plan durable caller adoption工作包

只把`assignment_plan_apply`切到frozen Core／bridge；不改Assignment Plan業務規則、worker、Jobs public route或DB。

## Exact write set

- `api/routes/assignment_plan.py`
- `tests/test_assignment_plan_durable_job.py`
- `tests/test_assignment_plan_durable_mysql_e2e.py`
- `tests/test_assignment_plan_workflow.py`（regression only）
- `document/架構重整/01_規格基線/01_Orders_Domain.md`（Integration Owner only；只記錄durable caller contract）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-assignment-plan-caller-adoption/`（new）。

## Acceptance

- exact command type/version/payload/actor mapping；同key同payload重播同identity，不同payload/actor/version typed 409。
- route不再直接依賴MySQL concrete repository，不吞`JobIdempotencyConflict`，0 hidden commit。
- disposable MySQL證明outer UoW、rollback、replay；JobAccepted不冒充assignment applied。
- 0 provider、0 DB schema、0 React。

DB：Scope BLOCKED待核准；Change inventory PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
