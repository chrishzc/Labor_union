---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening
date: 2026-08-17
owner: Finance Import
domain: Finance Import
approval_required: 核准此 exact Phase 4A-FI-H Work Package
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4A-FI-H：Finance Import／Bank Facts public contract hardening工作包

## Scope

本包同時是Finance Import三個command types的caller-adoption owner；若另立caller writer會與
`api/routes/finance_import.py`衝突，固定禁止平行施工。本包以已凍結Core／bridge完成payload equality、typed
conflict與outer UoW adoption，並收斂Finance bounded public contract。Job accepted不是terminal business success；
不改Finance Import Domain規則或DB schema。Global masked Public Outcome在六個caller adoption全部PASS後另行執行。

## Exact write set

- `api/routes/finance_import.py`
- `api/schemas/finance_import.py`
- `subsystems/finance_import/ingestion.py`
- `api/dependencies/finance_import.py`
- `tests/test_finance_import_public_contract.py`（new）
- `tests/test_finance_import_ingestion.py`
- `tests/test_finance_import_query.py`
- `tests/test_finance_import_disposable_mysql_e2e.py`
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4a-finance-import/`（new）

Global Durable Jobs的worker／repository／route／schema由先行工作包唯一擁有，本包不得修改。Finance
Import只能compose其凍結port；若不足，先回報`SCOPE_EXPANSION_REQUIRED`。Finance public contract必須提供bounded
`GET /api/v1/finance-import/jobs/{job_id}`，只接受Finance Import job，回strict discriminated terminal
receipt/error，不得把generic raw job payload穿透React。

本包必須逐一採用`finance_import_historical_reprocess_apply`、`finance_import_batch_apply`、
`finance_import_correction_apply`；禁止同步Apply fallback或把`JobIdempotencyConflict`轉成舊job成功。

## Acceptance

1. batch、manifest、review row、reprocess run、ingestion receipt皆strict Pydantic；status/classification/disposition/
   available-actions與field errors使用正式bounded literals/nested models，0 `Any`／raw map。
   Preview只回aggregate與bounded first page；row detail以cursor＋preview fingerprint查詢，pagination不得改變Apply candidate。
2. 全query/errors使用typed envelope、auth、correlation、cursor/request budget；Query 0 commit。
3. durable Apply只回JobAccepted；UI必查job、terminal receipt與canonical bank facts，禁止映射成「匯入成功」。
4. durable command fingerprint包含command type/version、canonical payload與actor policy；same key同fingerprint回原job，
   任一payload/actor差異typed 409。Finance workflow validation/conflict/domain-blocked為terminal durable error；
   只有正式unavailable且retryable才進retry，exhaustion保留最後去敏typed error與attempt count。
5. disposable MySQL驗bank facts、occurrence、classification、attempt audit、exact replay與failed transaction。
6. 不觸發真外部provider；完整銀行資料只由server-masked view輸出。
7. 移除production route的同步Apply fallback；controller不得因test double缺`enqueue_command`改變durable語意。

DB Gate：未核准Scope BLOCKED；核准且Global prerequisite PASS後Scope／Change inventory PASS（0 schema），
其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
