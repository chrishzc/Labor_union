---
doc_type: work-package
declared_status: proposed
identity: PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor
date: 2026-08-22
owner: Global Validation Governance Integration Owner / Scheduling
domain: Global Validation Governance / Scheduling
source_work_package: PROV-20260817-react-admin-phase3b-h-r-holiday-react
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow PASS
approval_required: 核准此 exact Phase 3B-H-R Holiday Mutation Scenario Lineage Successor Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: metadata-and-controlled-browser-receipt-normalization
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
db_change: none
---

# Phase 3B-H-R Holiday Mutation Scenario Lineage Successor

## Problem

已核准的H-R React工作包要求Holiday Query→Preview→Apply→receipt→re-query及stale／same-key replay／conflict／
rollback，但canonical `SCH-REACT-ADMIN-HOLIDAY-POLICY` revision 1仍只宣告query、zero-write、replay
not-applicable及no-browser-execution。現有implementation與disposable browser evidence不得反向覆蓋scenario SSOT。

## Exact write set

- `validation/scenarios/react_admin_holiday_policy.json`
- `validation/catalog/phase3_scenario_lineage.json`
- `validation/fixtures/phase3/SCH-REACT-ADMIN-HOLIDAY-POLICY.json`
- `validation/expected/phase3/SCH-REACT-ADMIN-HOLIDAY-POLICY.yaml`
- `validation/receipts/phase3/manifest.json`
- `validation/ui_business_workflows/part_09_scheduling/checklist.md`
- `validation/ui_business_workflows/part_09_scheduling/expected.yaml`
- `validation/ui_business_workflows/part_09_scheduling/result_summary.md`
- `tests/test_phase3_scenario_lineage.py`
- 本工作包、H-R工作包及其`open-findings.md`／`contract-matrix-freeze-receipt.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`

## Acceptance

1. 保留scenario identity，revision升為2；catalog、fixture、expected與receipt registry精確一致。
2. root inputs新增synthetic mutation command、expected calendar version、preview fingerprint、reason及stable
   idempotency identity；禁止直接seed receipt、projection或success state。
3. commands與oracles明列Query、zero-write Preview、Apply、receipt、post-commit re-query、same-key replay、stale、
   conflict、rollback及outcome-unknown recovery；browser mode改為controlled execution。
4. Part 09 checklist區分既有DB GET／Preview與owned disposable DB Apply；既有DB不得mutation。
5. result summary只能引用真實2026-08-22 receipt；未實跑的stale／conflict／rollback browser項目維持NOT_RUN，
   可由focused adapter／MySQL evidence支持其所屬層級，但不得冒充browser PASS。
6. Phase3 lineage validator、strict JSON/YAML、UTF-8/no BOM、secret/PII scan及scoped diff check PASS。
7. 不修改production code、API、schema、migration或既有資料庫。

## Completion boundary

本包完成後只解除H-R的scenario lineage blocker；H-R仍須由Integration Owner核對所有runtime receipts後才能轉PASS，
不自動授權Phase 5 entry switch。

## DB gate

Scope／Change inventory `PASS`（metadata only）；Static release、Descriptor、Read-only plan、Engine verification、
Developer acceptance均`NOT_RUN`；固定總結`DB_CHANGE_NOT_READY`。
