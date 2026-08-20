---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-durable-job-government-subsidy-caller-adoption
date: 2026-08-17
owner: Government Subsidy
domain: Government Subsidy
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS
approval_required: 核准此 exact Government Subsidy Durable Job Caller Adoption Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Government Subsidy durable caller adoption工作包

只收斂`government_subsidy_apply`及其closed action discriminator；不改補助金額／狀態規則、報表authority、worker、
Jobs public route或DB。

## Exact write set

- `api/routes/government_subsidy.py`
- `api/schemas/government_subsidy.py`（只在closed action/accepted view需對齊時）
- `tests/test_government_subsidy_durable_job.py`
- `tests/test_government_subsidy_durable_mysql_e2e.py`
- `tests/test_government_subsidy_api_client.py`（route regression）
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-government-subsidy-caller-adoption/`（new）。

## Acceptance

- action/payload/actor/version全部參與Core equality；不同action或payload不得重播舊job。
- route使用bridge，0 concrete repository、0 hidden commit、typed 409；accepted不冒充claim/receipt/reversal完成。
- disposable MySQL覆蓋所有核准action、replay/mismatch/rollback；0 provider、0 schema、0 React。

DB：Scope BLOCKED待核准；Change inventory PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
