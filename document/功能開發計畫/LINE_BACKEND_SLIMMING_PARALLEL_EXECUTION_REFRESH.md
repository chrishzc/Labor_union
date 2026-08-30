---
doc_type: execution-ssot-refresh
declared_status: in-progress
date: 2026-08-30
task_id: CUR-LINE-BACKEND-SLIMMING-01
owner: LINE / Integration
baseline_head: de7320ee859c472864a5e35eee4f492fde6429c6
task97_dependency: satisfied_repository_local
execution_authority: repository-local refactor and tests
parallel_lane: line
parallel_peer: CUR-ANOMALY-SLIMMING-01
---

# LINE Backend Slimming：current-head parallel execution SSOT refresh

## 1. Authority 與 current baseline

本檔是 `LINE_BACKEND_SLIMMING_PLAN.md`、`LINE_BACKEND_SLIMMING_POST_PREP_AMENDMENT.md`、
`LINE_BACKEND_STATE_AUDIT.md` 與 `LINE_BACKEND_RESOLVED_WRITE_SET.md` 在 Task 97 repository-local closeout後的
current execution successor。正式 owner／integration語意仍以
`17_External_Integration_LINE_Access正式規格.md` 為準；本檔只固定 current source facts、仍適用 write set、平行施工邊界與停止線。

- source execution baseline：`main@de7320ee859c472864a5e35eee4f492fde6429c6`
- Task 97：`TASK97_REPOSITORY_LOCAL_COMPLETE`
- current source baseline CI：GitHub Actions run `33305210601` success；build、governance、cross-domain、12-owner matrix均通過。
- 本次人工 Authority：恢復 LINE backend slimming repository-local S0～S9 execution，允許與 Anomalies slimming平行。
- 不授權：provider真實呼叫、production／`union_db`、deployment、entry switch、schema drop、historical data deletion、Task 96 M1～M4新功能。

本次新增的 Anomalies／LINE refresh文件若位於上述 source baseline之後，只是 docs-only coordination；Agent正式開工前仍必須從當時 current `main` rebase並確認 production source drift。

## 2. Refreshed S0／S1 current facts

舊 inventory counts不再直接沿用；以下是 current HEAD已重新確認的 executable facts。

### 2.1 Cross-domain direct mutation仍存在

1. `infrastructure/mysql/line_order_group_adapters.py::set_group_projection()` 仍直接：

```sql
UPDATE orders SET line_group_id=...
```

因此 Orders `line_group_id` projection family仍是 current S2 rewrite target。

2. `subsystems/line/identity_review_workflow.py::complete_client_binding_in_transaction()` 仍直接：

```sql
UPDATE clients SET line_user_id=...
```

而同一 legacy workflow仍使用 legacy `enqueue_line_task`。因此 legacy client binding／review direct-write family仍未被Task 97吸收完成。

### 2.2 Legacy delivery path仍有 current callers

`subsystems/line/delivery_task_workflow.py` 不能直接刪除。Current code search仍有 inbound callers，包括：

- `line/line_bot.py`
- `subsystems/line/identity_review_workflow.py`
- `subsystems/scheduling/matching_communication_workflow.py`
- `subsystems/scheduling/candidate_contact_pool_workflow.py`
- legacy Rich Menu／LINE paths

所以 S3 必須先 caller-by-caller改接 canonical delivery port，再做 module zero-reference gate。

### 2.3 Provider duplication仍存在

Current source仍可找到 direct `api.line.me` provider calls於：

- `line/worker.py`
- `subsystems/line/rich_menu_publication_workflow.py`

Canonical provider adapters仍是：

- `infrastructure/line/messaging_api_adapter.py`
- `infrastructure/line/rich_menu_api_adapter.py`

因此 messaging與Rich Menu provider各自仍有 canonical＋legacy雙路徑；S4／S6 convergence仍適用。

### 2.4 Task 97 absorbed items

Task 97 已處理的 repository／route UoW、entry classification、global writer governance、canonical test architecture、LINE admin typed contract不得重做。
Public unknown-caller entries依 Task 97 final disposition保留 typed 410／guarded identity，LINE slimming不得只因static caller=0 physical delete。

## 3. Refreshed execution order

原S0～S9概念保留，但current execution切成 bounded packages：

### LINE-P1：S2 cross-domain ownership removal

優先處理兩個已確認 direct-write families：

- Orders `line_group_id` projection writer
- legacy client binding／review direct Client write

目標：LINE只寫LINE-owned roots；Orders／Client projection經 owner typed boundary或owner-owned projection adapter完成。
不得新增 generic owner mutation API。

### LINE-P2：S3/S4 delivery convergence

逐 current caller把 `delivery_task_workflow`／legacy `line_tasks` enqueue改接 canonical delivery task port。
Caller未清零前不得刪 module；`line/worker.py` legacy runtime若仍為registered rollback mode只可 `retain-restricted`，不能physical delete。

### LINE-P3：S5 identity slimming

移除單一 role authority與legacy review state machine的 business ownership；保留LINE platform identity、binding root、review/revocation與正式 owner projection ports。

這個 package同時負責提供 Anomalies peer 所需的 LINE-004 owner-side typed query/action contract；不得修改 anomaly registry／projection。

### LINE-P4：S6 Rich Menu convergence

public routes保持既有 typed contract，但 publication只走 canonical application／worker／provider adapter。
先移除 subsystem direct provider call，再做 legacy workflow zero-reference。

### LINE-P5：S7/S8/S9 dead code／transient／tests closeout

只刪 exact caller=0且replacement／retention gate完成的 speculative AI／legacy source；current deterministic routing、Knowledge integration、provider history、migration provenance保留。

完成後跑 LINE canonical root、affected cross-domain、build／governance／12-owner、full non-engine Python與affected React gates。

## 4. LINE-004／LINE-006 對 Anomalies peer 的 contract responsibility

兩個平行 Agent之間只有 typed contract依賴，不共寫 source：

- LINE Agent擁有 `LINE-004` identity/binding current facts、合法client＋staff雙角色判定所需 typed Query／version／readback。
- LINE Agent擁有 `LINE-006` terminal delivery／configuration failure、retry state、manual retry／configuration correction所需 typed Query／action/readback。
- Anomalies Agent只擁有 current issue detector／projection／typed descriptor consumer。

若本 LINE branch尚未merge，Anomalies peer可標 `WAIT_PEER_LINE_CONTRACT`；不得因此直接改 LINE internals。

## 5. Parallel write set — LINE Agent 專屬

可修改：

- `domains/line/**`
- `subsystems/line/**`
- `infrastructure/line/**`
- `infrastructure/mysql/line_*`
- `api/routes/line_*`
- `api/dependencies/line_*`
- `api/schemas/line_*`
- `line/**`
- `tests/domains/external-integration/subsystems/line/**`
- LINE-specific higher-boundary tests
- `config/` 中只屬LINE bootstrap／compatibility且被本 package明確命中的檔案
- 本 LINE execution SSOT／LINE專屬 receipt

允許 bounded cross-owner change，但只能在本計畫已列明：

- Orders query/projection adapter為移除 `orders.line_group_id` direct write所需的最小改動
- Scheduling caller只為把 legacy LINE delivery enqueue改接 canonical LINE delivery port所需的最小改動

任何上述 cross-owner修改都必須保持 owner business semantics不變並跑對應 owner tests。

禁止修改 Anomalies peer write set：

- `domains/anomalies/**`
- `subsystems/anomalies/**`
- `infrastructure/mysql/*anomaly*`
- `api/routes/anomaly*`
- `api/dependencies/anomaly*`
- `api/schemas/anomaly*`
- Anomalies canonical tests

## 6. Shared hot spots — 兩個 Agent 都不得直接寫

只由最後 integration writer收斂：

- root `README.md`
- `document/功能開發計畫/README.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- Task 97 entry／writer／production-script／commit artifacts與generators
- `.arch-map/index.md`、`.arch-map/meta.yaml`
- `.github/workflows/**`
- `api/main.py`
- generic `subsystems/jobs/**`
- `db/schema_parts/**`、migration／release／fresh assembly

需要shared hot spot時只記 `INTEGRATION_WRITER_FOLLOWUP`。

## 7. Delete／retention gate

LINE slimming仍不授權：

- drop `line_tasks`／legacy webhook／identity／review tables
- drop `orders.line_group_id`
- 刪 provider／identity／review／audit歷史資料
- physical delete external caller未知的public entry
- 修改published migration chain

source delete只限：current inbound caller=0、replacement存在、focused regression通過、entry／retention gate不需要保留runtime identity。

## 8. Completion

Repository-local LINE slimming完成需同時滿足：

- current direct cross-domain business writes清零或全部變成正式 owner projection adapter契約。
- canonical messaging provider send path唯一。
- canonical Rich Menu provider path唯一。
- legacy delivery／identity／review executable source完成 exact keep／rewrite／delete disposition。
- LINE-004／LINE-006 owner-side typed contract可供Anomalies peer使用。
- LINE canonical tests、受影響Orders／Scheduling boundary、build／governance、12-owner matrix通過。
- shared hot spot follow-up由integration writer收斂。

DB／production／provider acceptance保持deferred，不得偽裝PASS。

```text
LINE_BACKEND_SLIMMING_PARALLEL_EXECUTION_READY
DESTRUCTIVE_RETENTION_NOT_AUTHORIZED
```
