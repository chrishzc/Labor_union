---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-durable-job-persistence-caller-adoption-decision
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
source_gap: PROV-20260817-durable-job-persistence-caller-adoption-decision-gap
authority: exact-human-approved-option-a
activation_state: decision-complete-option-a-conditional
prerequisites: none
approval_required: 核准此 exact Durable Job Persistence / Caller Adoption Decision Work Package，採用 Option A
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
approved_at: 2026-08-21
completed_at: 2026-08-21
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Durable Job persistence／caller adoption docs-only決策工作包

## 0. Approved decision

2026-08-21人工exact核准`Option A：Existing-column canonicalization`。現有queue已保存command type、version、JSON payload、
submitted actor與correlation；先以這些欄位建立canonical equality與closed terminal serialization，避免在尚未證明
需要新欄位前擴張schema。此決策不授權production code；若真MySQL matrix證明現有欄位無法無歧義承載契約，
固定改判`BLOCKED_DB_SUCCESSOR_REQUIRED`，另立additive migration successor。

本包完成輸出固定為`DECISION_COMPLETE_OPTION_A_CONDITIONAL`：只代表Global契約、successor順序及engine
驗證方法已凍結，不代表Core／Bridge／caller／public outcome／React runtime完成，也不代表MySQL engine PASS。

## 1. Exact write set（docs／evidence only）

- 本工作包
- `PROV-20260817-durable-job-persistence-caller-adoption-decision-gap.md`
- `PROV-20260817-durable-job-public-outcome-contract-work-package.md`（只回寫activation/resulting split）
- `document/架構重整/01_規格基線/00_Global_共同契約.md`（只加入核准的Global Job equality／UoW裁決）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-persistence-caller-adoption-decision/persistence-caller-matrix.md`（new）
- 同目錄`decision-receipt.md`與`open-findings.md`（new）

禁止修改Python、SQL、React、tests、validation fixtures、DB、migration或任何runtime entry。

## 2. Required matrix

逐欄比對`background_jobs`現有schema、`DurableJobCommand`、repository insert/read/claim/complete/fail paths及
public Job view，明確回答：

1. canonical equality是否可固定為`command_type + command_version + canonical_payload + submitted_by`；
   correlation ID只作觀測，不參與business equality。
2. MySQL JSON round-trip能否保持canonical payload等價；數字、null、object key order、array order與Unicode的規則。
   Option A canonical JSON固定只接受object、string keys與finite JSON values，reject NaN/Infinity；serialization
   使用UTF-8、`ensure_ascii=False`、sorted keys、compact separators及`allow_nan=False`。Typed schema下`1`與
   `1.0`視為不同payload；若MySQL round-trip無法保持此差異，Option A固定FAIL並要求DB successor。
3. `background_jobs.command_identity`使用case-insensitive collation；canonical Durable Job idempotency key固定
   必須先符合lowercase ASCII `^[a-z0-9][a-z0-9._:-]{0,190}$`。Uppercase在進DB前拒絕，不得silent lowercase；
   各caller adoption負責入口驗證，legacy uppercase key不得進canonical path。若此契約不可接受，Option A固定
   `BLOCKED_DB_SUCCESSOR_REQUIRED`，不得讓`Key`／`key`碰撞後冒充replay。
4. canonical `submitted_by`使用immutable actor identity（例如`admin_user_id:<positive-id>`或核准的
   `system:<owner>`），case-sensitive且不得使用display username；缺immutable identity的caller由adoption阻擋。
5. receipt/error JSON如何使用closed command-type discriminator與schema version，不回raw map。
6. repository hidden commit如何退場，唯一outer UoW／commit owner在哪一層。
   必須把`api/dependencies/private_operations.py::run_durable_job_cycle`列入composition matrix，裁決worker與
   runtime heartbeat是否同一transaction，不能只看worker/repository兩層。
7. 六個enqueue owner檔、八種command type逐一列出：Assignment Plan；Finance Import batch/correction/
   historical reprocess；Government Subsidy（含各action payload）；Payroll Rebuild；Staff Payout；Orders Auto
   Completion。每一caller都要記錄same-key replay、mismatch exception與HTTP／subsystem typed conflict adoption路徑。
8. 哪些caller可共用一個application port，哪些仍需bounded route/schema test；不得以Global route測試替代。

## 3. Resulting successor rule

若Option A PASS，後續固定序列化為：

1. Core Persistence／Worker contract；
2. Caller Integration Bridge；
3. 六個enqueue owner／八種command type的exact bounded caller adoption；
4. masked public observation；
5. 各React bounded consumer。

任一production successor都必須有exact caller paths、tests與shared-hot-spot owner。若Option A FAIL，只建立
additive DB successor；必須完整執行schema release、descriptor、read-only plan、fresh bootstrap、preserve-data
candidate與developer acceptance gates，不能回頭把SQL塞進原工作包。

## 4. Acceptance／anti-fake gates

- G0：exact approval、dirty preservation、0 production/test/SQL path。
- G1：schema／command／repository／worker／public view逐欄矩陣完成。
- G2：全部durable enqueue callers與現有catch/replay行為列全；不得只列五個route檔名而漏同檔多個command。
- G3：以`JOB-DURABLE-001`／`JOB-QUEUE-LIFECYCLE-002`記錄adoption／supplement／test-data gap。
- G4：Option A每個必要條件有source與真MySQL可驗證方法；不能以Python `json.dumps`單元測試冒充DB round-trip。
- G5：輸出唯一decision receipt、resulting production WPs與exact approval文字；不把docs-only完成稱為runtime完成。
- G6：strict UTF-8、reference identity、inbound links與write-set audit通過。

## 5. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope | PASS | docs-only architecture decision |
| Change Inventory | PASS | 0 schema／seed／backfill／destructive |
| Static Release | NOT_RUN | Option A不建release；Option B另案 |
| Descriptor | NOT_RUN | 同上 |
| Read-only Plan | NOT_RUN | 同上 |
| Engine Verification | NOT_RUN | 本包只定義後續真MySQL驗證方法 |
| Developer Acceptance | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。
