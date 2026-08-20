---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract
date: 2026-08-17
owner: Case Import / Global Transaction Governance
domain: Case Import / Anomalies
source_gap: PROV-20260816-react-admin-phase4a-hcm-backend-transaction-receipt-gap
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-case-import-workbook-policy-decision PASS
activation_blocker: PROV-20260817-case-import-workbook-atomicity-archive-policy-gap
approval_required: 核准此 exact Phase 4A-H Work Package，並採用 HCM Source Archive Option A
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4A-H：HCM Apply transaction／warning／receipt backend 工作包

## 0. 狀態與推薦裁決

本包為proposed，推薦採用Source Archive Option A。核准後只修backend；`imports.hcm-current.apply`
仍維持native disabled，直到後續React Apply工作包與controlled browser通過。

不可接受「每列commit＋aggregate receipt」。正式目標為整本workbook單一outer UoW。技術／不變量失敗整本
rollback；可預先判定的review／warning是terminal row disposition，必須與合法root、review、outbox、receipt
在同一commit保存，不得被誤判為整檔技術失敗。

本包在Case Import裁決缺口關閉前不得啟動。該缺口必須先裁決「IP＋姓名命中既有Client」是
`review_only`或`create_partial_case_plus_warning`，以及各workbook family的archive／atomicity政策。

## 1. Transaction invariant

`HcmCurrentWorkbookApplyWorkflow`是唯一outer UoW owner：lock workbook claim → fresh rebuild Preview candidate → validate source/identity/version → 經borrowed Case Import
persistence ports套用各列 → append warning review/outbox intents → persist terminal workbook receipt → one commit。

repository/intake/archive metadata adapter不得begin／commit／rollback；不得呼叫`HcmLegacyRowIntake`、
`_process_import_rows`、`_import_row`、`record_hcm_import_review`或逐列自行commit的`CaseImportApplication.apply`。
borrowed ports只接受workflow持有的transaction context；provider/warning projection worker只消費commit後intent。

Preview fingerprint不能只由檔案digest與aggregate counts組成。每個去敏candidate至少納入source identity、source
payload digest、mapping revision、identity-resolution disposition、target expected version與warning/review disposition。
Apply必須在同一outer UoW鎖定全部受影響roots、mapping與source identities，使用同一builder重建candidate；
任一項漂移固定typed stale且零寫入。

## 2. Public contract

- Preview與Apply維持multipart workbook；Apply必須帶Idempotency-Key、X-Correlation-ID、
  X-Preview-Fingerprint與trim後1–500字`reason`；reason納入canonical command fingerprint。
- 新增authenticated receipt lookup：`GET /api/v1/case-import/hcm/workbooks/receipts/current`，
  key/correlation走headers，不放URL。
- receipt只含digest、row count、preview fingerprint、五類aggregate count與replayed flag；禁止row內容/PII/raw warning。
- `/workbooks/ingest`與historical whole-row overwrite都必須正式回Global typed 410；不得只從React client排除legacy writer。
- typed errors與cleanup outcome不得用raw `detail.code`或把post-commit cleanup失敗冒充Domain失敗。
- Archive Option A採`not_started → archived → db_committed`，失敗分支為
  `compensation_pending → compensated | anomaly_open`。archive identity為source content digest＋policy revision；
  write/delete必須idempotent。receipt只保存去敏archive reference/digest，不保存local path、filename或raw workbook。
  archived後crash、commit後cleanup失敗及compensation失敗都必須可由authenticated operator查詢安全結果。

## 3. Exact production write set

- `api/routes/hcm_import.py`
- `api/schemas/hcm_import.py`
- `api/dependencies/hcm_import.py`
- `subsystems/case_import/hcm_workbook_import.py`
- `subsystems/case_import/hcm_current_workbook_intake.py`（new）
- `subsystems/case_import/case_import_workflow.py`
- `subsystems/case_import/application.py`
- `subsystems/case_import/hcm_import_review_intake.py`
- `infrastructure/mysql/hcm_workbook_import_repository.py`
- `infrastructure/mysql/case_import_repository.py`
- `infrastructure/mysql/hcm_import_review_repository.py`
- `infrastructure/archive/hcm_workbooks.py`（new；Option A）

Source archive policy與持久化能力必須在G0 static inventory中先證明可由既有schema表達；若無法保存
`archived → db_committed | compensation_pending → compensated | anomaly_open`，固定`DB_SCOPE_REQUIRED`並停止，
不得以local log、temp file或evidence文件冒充durable recovery state。

## 4. Exact test write set

- `tests/test_hcm_workbook_import.py`
- `tests/test_hcm_import_router.py`
- `tests/test_hcm_import_api_client.py`
- `tests/test_hcm_import_safety_gate.py`
- `tests/test_hcm_import_api_disposable_mysql_e2e.py`
- `tests/test_case_import_disposable_mysql_e2e.py`
- `tests/test_hcm_import_warning_occurrences.py`
- `tests/test_import_warning_tracking_disposable_mysql_e2e.py`
- `tests/test_hcm_workbook_outer_uow_disposable_mysql_e2e.py`（new）
- `tests/test_hcm_import_public_contract.py`（new）
- `tests/test_hcm_workbook_archive.py`（new；Option A）
- `tests/test_hcm_workbook_no_legacy_writer.py`（new）

DB/schema、React、Streamlit、shared transport/Auth、CLI retirement不在範圍。靜態inventory若證明既有table不足，
固定`DB_SCOPE_REQUIRED`並停止production writer。

## 4.1 Integration document write set

- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- source archive decision gap、本工作包與`02/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract/`（new）

public contract/archive policy只由Integration Owner更新。

## 5. Execution protocol

- Contract/transaction/source-archive matrix由Primary freeze。
- 同一Backend Owner串行修改所有production transaction hotspots。
- Terra只在interface freeze後補disjoint tests，不修改production。
- Luna唯讀驗證hidden commit、stale test、PII、write-set、tests。
- Integration Owner唯一修改規格/index/evidence。

## 6. G0–G8

- G0 exact approval含Archive Option A；0 React/DB scope drift。
- G1 multipart Preview/Apply/receipt/error/archive逐欄矩陣strict frozen，含source identity、mapping revision、
  target expected version、PII class、archive state與terminal disposition。
- G2 whole-workbook one outer UoW；0 repository/intake hidden commit。
- G3 Apply fresh rebuild；Preview後新增同案、mapping/identity/warning disposition漂移、duplicate皆fail closed且零寫入。
- G4 warning review/outbox同transaction；0 fake row/task IDs。
- G5 exact replay同receipt；changed payload/key conflict；0 duplicate roots/reviews/outbox。
- G6 任一技術／不變量／case/review/receipt failure全部rollback；可預判review row保存為terminal disposition；
  archive crash/cleanup/compensation符合Option A。
- G7 auth/error/receipt lookup/cleanup typed；legacy ingest與historical route皆正式typed 410。
- G8 disposable MySQL、archive、full focused regression、UTF-8、diff、secret/PII/full audit。

## 7. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4ah-hcm -q `
  tests\test_hcm_workbook_import.py tests\test_hcm_import_router.py tests\test_hcm_import_api_client.py `
  tests\test_hcm_import_safety_gate.py tests\test_hcm_import_public_contract.py `
  tests\test_hcm_workbook_outer_uow_disposable_mysql_e2e.py tests\test_hcm_import_api_disposable_mysql_e2e.py `
  tests\test_case_import_disposable_mysql_e2e.py tests\test_hcm_import_warning_occurrences.py `
  tests\test_import_warning_tracking_disposable_mysql_e2e.py tests\test_hcm_workbook_archive.py
git diff --check
```

skip disposable MySQL或archive test時對應gate固定BLOCKED，不得稱completed。

## 8. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | archive/recovery persistence尚未證明可由既有tables表達；命中`DB_SCOPE_REQUIRED`時必須另立DB successor |
| Change inventory | PASS | 目前exact write set為0 schema/seed/backfill/destructive；static persistence inventory尚未完成 |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | whole-workbook rollback必須真MySQL |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
