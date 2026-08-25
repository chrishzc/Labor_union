---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-durable-job-core-persistence-worker-contract
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-durable-job-persistence-caller-adoption-decision PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance completed with PHASE4_SCENARIO_LINEAGE_METADATA_READY
activation_state: completed-local-validated
authority: exact-human-approved-completed
approval_required: 核准此 exact Durable Job Core Persistence / Worker Contract Work Package
approved_at: 2026-08-22
completed_at: 2026-08-22
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
dirty_baseline: required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
ui_execution_mode: not-applicable
---

# Durable Job Core Persistence／Worker Contract 工作包

## 0. Scope

只建立 canonical command equality、closed terminal outcome與無hidden-commit的新Global queue repository/worker port。
本包不切換任何既有caller、不提供public HTTP、不接React、不呼叫provider、不修改DB。legacy callers在各自adoption
successor完成前維持原路徑，故本包完成不得宣稱system-wide durable job contract完成。

Core只保證recovery、claim、terminal transition與heartbeat等queue lifecycle各自由具名outer UoW擁有；現有8個
Domain handlers仍開自己的connection/UoW，因此Core不得宣稱Domain command與queue terminal outcome同一交易或
exactly-once。該閉合由六個caller-adoption successors逐一證明。

## 1. Exact production write set

- `shared_kernel/durable_job_queue.py`
- `subsystems/jobs/contracts.py`（new）
- `subsystems/jobs/ports.py`（new）
- `subsystems/jobs/durable_job_worker.py`
- `infrastructure/mysql/background_job_repository.py`
- `api/dependencies/private_operations.py`（只限durable worker composition、transaction／connection ownership；
  Knowledge／LINE／monitor composition不得改動）

## 2. Exact test／evidence write set

- `tests/test_durable_job_core_contract.py`（new）
- `tests/test_durable_job_worker.py`
- `tests/test_background_job_repository_mysql.py`
- `tests/test_durable_job_payload_equality_disposable_mysql_e2e.py`（new）
- `tests/test_durable_job_disposable_mysql_e2e.py`
- `tests/test_private_runtime_operations.py`（只補durable worker composition／commit owner regression）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-core-persistence-worker-contract/`（new）
- 本工作包、原Public Outcome工作包resulting split、正式Global規格與索引只由Integration Owner更新。

禁止修改`api/routes/jobs.py`、`api/schemas/jobs.py`、`api/dependencies/jobs.py`、所有Domain caller、React、SQL、
migration、provider與shared Auth。

## 3. Frozen invariants

- equality固定為command type＋version＋canonical payload＋submitted actor policy；correlation只作觀測。
- canonical key只接受lowercase ASCII contract；uppercase在DB前拒絕。Canonical payload只接受JSON object、
  string keys與finite values，reject NaN/Infinity；serialization固定`ensure_ascii=False`、`sort_keys=True`、
  `separators=(",", ":")`、`allow_nan=False`，且`1`與`1.0`不同。Actor使用case-sensitive immutable canonical
  `submitted_by` identity，不得以display username代替。任一MySQL round-trip/collation不符合核准決策即
  `BLOCKED_DB_SUCCESSOR_REQUIRED`。
- same key/same equality回相同identity；type/version/payload/actor任一差異為typed conflict。
- legacy NULL／無法重建equality的row fail closed，不猜測相等。
- terminal receipt/error為closed discriminated union並帶schema version；success只保存allowlisted
  `result_reference`，failure只保存去敏typed error，不得穿透raw map、handler receipt、`str(error)`或traceback。
- 新canonical repository methods不commit／rollback；worker application是其transaction的唯一commit owner。
- 不直接移除legacy methods的commit語意，避免尚未adopt的caller在connection close時被rollback。
- canonical reader對command type/version/payload/submitted_by/correlation任一NULL、invalid JSON或wrong type
  fail closed；不得補`system`、`job:<id>`或`{}`。Legacy methods維持原語意但不得進canonical path。
- worker retry／exhaustion／crash-resume不能把accepted、processing、provider ack、Domain receipt合併為success。

## 4. Acceptance

1. Python與真MySQL驗JSON number/null/object key order/array order/Unicode round-trip equality。
2. safe negative control先證明舊same-key/different-payload可被誤接納，再由新port fail closed。
3. 新canonical methods（名稱不得與legacy hidden-commit methods相同）0 commit/rollback。Recovery、claim、
   terminal transition、heartbeat各有具名begin/commit/rollback/close owner；heartbeat failure不得抹除已提交terminal
   outcome。Core不把Domain handler交易與terminal transition宣稱原子；Knowledge／LINE／monitor composition保持不變。
4. 0 provider call；0 public API；0 Domain caller行為變更。
5. MySQL case不得skip；使用唯一`lu_test_*` disposable fixture且禁止`union_db`。測試直接驗same-key replay、
   type/version/payload/actor mismatch、Unicode/null/object/array/number、`Key`/`key` collation、legacy NULL、
   crash-resume與canonical methods零hidden commit。缺環境固定`BLOCKED_ENGINE_EVIDENCE`。
   `tests/test_background_job_repository_mysql.py`必須以module/session scoped唯一disposable DB bootstrap，禁止每個
   test重建同一既存DB或因既存DB而skip。
6. evidence列出6個enqueue owner檔與8種command type，全部保持`awaiting-caller-adoption`。
7. strict UTF-8、diff、secret/raw-map/weak-test/write-set audit通過。
8. crash發生於Domain handler完成與queue terminal transition之間時，只能保留pending/recovery觀測並交由
   caller-adoption successor收斂；Core不得以此宣稱Domain side effect exactly-once。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | Option A、Phase4 metadata prerequisite、exact本包核准與fresh base audit均已完成 |
| Change Inventory | PASS | 0 schema／seed／backfill／destructive |
| Static Release | NOT_RUN | 無release |
| Descriptor | NOT_RUN | 無schema變更 |
| Read-only Plan | NOT_RUN | 不適用 |
| Engine Verification | PASS | 3個唯一`lu_test_*` queue-only DB；12個MySQL cases驗證round-trip、collation、replay、conflict與crash-resume後已各自清除 |
| Developer Acceptance | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

## 6. Completion record（2026-08-22）

本 exact Core 工作包已完成 canonical equality、closed terminal outcome、canonical repository port 與 worker
outer transaction ownership。新 canonical methods 沒有 hidden commit／rollback；recovery、claim、terminal
transition 由 worker 分別提交，heartbeat 另由 private composition 在 terminal commit 後持有獨立 transaction。

Final focused verification：

```text
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\durable-core-final -q tests\test_phase4_scenario_lineage.py tests\test_durable_job_core_contract.py tests\test_durable_job_worker.py tests\test_background_job_repository_mysql.py tests\test_durable_job_payload_equality_disposable_mysql_e2e.py tests\test_durable_job_disposable_mysql_e2e.py tests\test_private_runtime_operations.py
86 passed in 7.93s
```

本完成紀錄只適用 Core：沒有切換 caller、public jobs route、React、provider 或 production；8 個 handler 仍各自
持有 Domain connection/UoW，故 Domain command 與 queue terminal transition 不宣稱 atomic 或 exactly-once。
