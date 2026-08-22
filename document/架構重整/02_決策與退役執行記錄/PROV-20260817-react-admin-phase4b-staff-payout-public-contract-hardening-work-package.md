---
doc_type: work-package
declared_status: in-progress
activation_state: durable-caller-prerequisite-completed-broader-sp-h-open
durable_job_caller_adoption_state: completed-local-validated-2026-08-22
authority: user-approved-in-spec-auto-activation-2026-08-22
identity: PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening
date: 2026-08-17
owner: Staff Payables
domain: Staff Payables
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS
approval_required: 核准此 exact Phase 4B-SP-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 4B-SP-H：Staff Payout public contract／durable outcome工作包

## Activation boundary

本包同時是`staff_payout_apply` caller-adoption owner；若另立caller writer會與`api/routes/staff_payout.py`
衝突，固定禁止平行施工。它使用已凍結Core／bridge完成same-key equality、typed conflict與outer UoW adoption，
並收斂Staff Payout bounded contract；不得以raw Jobs route或job accepted冒充terminal payout receipt。Global
masked Public Outcome在六個caller adoption全部PASS後另行執行。

## Exact production write set

- `api/routes/staff_payout.py`
- `api/schemas/staff_payout.py`

## Exact test／doc write set

- `tests/test_staff_payout_public_contract.py`（new）
- `tests/test_staff_payout_api_client.py`
- `tests/test_staff_payout_reconciliation_workflow.py`
- `tests/test_staff_payout_durable_job.py`
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md`（Integration Owner only）
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4b-staff-payout/`（new）

## Acceptance

1. Preview candidate、payout/event/resulting status改成bounded views/literals；public response 0 raw dict。
2. 明確區分`202 JobAcceptedResponse`與terminal payout receipt；job status、receipt lookup、re-query與outcome_unknown
   必須使用先行Global Jobs凍結的strict public contract，不能在本包自行發明或解碼raw dict。
3. Preview 0 write；Apply fresh-read、single outer-UoW、idempotency、stale/replay/conflict保持Domain權威。
4. timeout只能同payload/key retry；job accepted不得映射成paid，provider/worker failure不得偽造Domain回滾。
5. route/workflow/durable job/disposable MySQL測試及server masking通過；銀行資訊不進raw UI contract。
6. React successor另案；本包完成不等於Finance entry cutover。
7. Scenario映射固定覆蓋Part 00 P00-G47／G50／G53／G54。
8. `staff_payout_apply`不得吞`JobIdempotencyConflict`；route不直接依賴MySQL concrete repository，disposable
   MySQL證明same-key replay／mismatch／outer UoW rollback。

DB Gate：Scope PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
