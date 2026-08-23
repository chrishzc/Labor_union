---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening
date: 2026-08-17
owner: Finance Import
domain: Finance Import
activation_state: blocked-prerequisites
durable_job_caller_adoption_state: completed-local-validated-2026-08-22
fixture_authority_state: blocked-test-data-authority
authority: exact-human-approved-blocked-prerequisites
approval_required: 核准此 exact Phase 4A-FI-H Work Package
approved_at: 2026-08-21
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance completed with PHASE4_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge proposed / approval-ready-refrozen
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

本包已於2026-08-21取得exact human approval；目前狀態為`approved / blocked-prerequisites`，不得立即啟動writer。Current hard
prerequisites中Phase4 Scenario Lineage已輸出`PHASE4_SCENARIO_LINEAGE_METADATA_READY`，Durable Job Core
Persistence/Worker已`completed-local-validated`，Global FastAPI Typed Error Boundary已`completed`；Durable Job Caller
Integration Bridge仍為`proposed / approval-ready-refrozen`。Bridge取得 exact approval 並完成，且Finance XLSX fixture authority與disposable evidence成立後，Integration Owner才可重新
捕捉dirty/collision並把activation改為active。

人工核准同時重申writer activation必須具備以下四項fresh evidence，任一缺失即維持blocked：

1. Phase4 Scenario Lineage完成其正式metadata lineage gate（已完成；不代表runtime PASS）；
2. Durable Job Core完成（已完成；不代表caller adoption）；
3. Durable Job Caller Bridge完成；
4. 合法Finance fixture與disposable DB evidence完成。

本核准不授權建立或上傳Finance XLSX、不授權操作既有DB，也不把Scenario Lineage metadata-ready升格為runtime PASS。

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

## G0–G7

| Gate | PASS condition |
|---|---|
| G0 | exact approval、全部hard prerequisites fresh PASS、base/dirty/collision re-freeze；既有DB/browser upload/provider禁止 |
| G1 | 三種Finance command、bounded Preview/detail、Finance-only job query與strict response models凍結 |
| G2 | Query/Preview零commit；typed auth/correlation/cursor/request budget；0 `Any`／raw map |
| G3 | Apply只回202 JobAccepted；移除同步fallback；same-key exact replay，payload/actor漂移typed 409 |
| G4 | worker唯一outer UoW owner；fresh-lock rebuild；terminal/retry分類及attempt evidence exact |
| G5 | 專屬disposable MySQL驗bank facts、occurrence、classification、attempt audit、replay與rollback；existing DB writes=0 |
| G6 | 0 provider；server-masked view；React mutation與browser XLSX upload維持disabled |
| G7 | focused public/subsystem/query/disposable tests、UTF-8/header/diff/PII/secret scan與evidence PASS |

## Finance XLSX fixture authority

目前`tests/test_finance_import_disposable_mysql_e2e.py`會在`tmp_path`動態合成多個XLSX，只能作mechanical parser
regression，不能冒充正式規格要求的去識別真實銀行格式產品驗收證據。若「不得合成／upload測試XLSX」限制適用
Finance，G5固定`BLOCKED_TEST_DATA_AUTHORITY`，直到人工提供或核准最小、去識別、可版本化、可重播的Finance fixture。
本包不得自行生成、上傳或從既有DB反向匯出workbook，也不得以mock/CSV取代G5。

## Current gate

| DB gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 2026-08-21 exact approval已取得；writer activation仍由四項hard prerequisites獨立阻擋 |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；existing DB writes固定0 |
| Static release | NOT_RUN | 無schema release |
| Descriptor | NOT_RUN | 無owned-object變更 |
| Read-only plan | NOT_RUN | 不適用migration |
| Engine verification | BLOCKED | disposable MySQL與Finance XLSX fixture authority未完成 |
| Developer acceptance | NOT_RUN | 禁止操作既有DB |

總結：`DB_CHANGE_NOT_READY`。
