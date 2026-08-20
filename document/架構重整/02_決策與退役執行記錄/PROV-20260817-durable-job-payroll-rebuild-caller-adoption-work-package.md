---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-durable-job-payroll-rebuild-caller-adoption
date: 2026-08-17
owner: Payroll
domain: Payroll
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS
approval_required: 核准此 exact Payroll Rebuild Durable Job Caller Adoption Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Payroll Rebuild durable caller adoption工作包

只把`payroll_rebuild_apply`切到Core／bridge；不改薪資公式、worker、Jobs public route、React或DB。

## Exact write set

- `api/routes/payroll_rebuild.py`
- `api/schemas/payroll_rebuild.py`（只在accepted/typed error view需對齊時）
- `tests/test_payroll_rebuild_durable_job.py`
- `tests/test_payroll_rebuild_durable_mysql_e2e.py`
- `tests/test_payroll_rebuild_workflow.py`（regression only）
- `document/架構重整/01_規格基線/03_Payroll_Domain.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-payroll-rebuild-caller-adoption/`（new）。

## Acceptance

- exact type/version/payload/actor equality與same-key replay/mismatch typed 409。
- route不依賴concrete repository，0 hidden commit；accepted不冒充payroll rebuilt。
- disposable MySQL驗outer UoW/replay/rollback；0 provider、0 schema、0 React。

DB：Scope BLOCKED待核准；Change inventory PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
