---
doc_type: execution-ssot-refresh
declared_status: in-progress
date: 2026-08-30
task_id: CUR-ANOMALY-SLIMMING-01
owner: anomalies / owning-domains
baseline_head: de7320ee859c472864a5e35eee4f492fde6429c6
task97_dependency: satisfied_repository_local
execution_authority: repository-local implementation and tests
parallel_lane: anomalies
parallel_peer: CUR-LINE-BACKEND-SLIMMING-01
---

# Current-state Anomalies：current-head parallel execution SSOT refresh

## 1. Authority 與 current baseline

本檔是 `PROV-20260829-current-state-anomaly-slimming-execution-plan.md`、post-prep amendment 與
`PROV-20260830-current-state-anomaly-task97-authority-reconciliation.md` 在 Task 97 repository-local closeout 後的
current execution successor。正式產品語意仍以 `06_Anomalies_Domain.md` 為準；本檔只把 current HEAD、已吸收成果、
剩餘 repository-local work、平行 write set 與停止線固定成可施工 SSOT。

- execution baseline：`main@de7320ee859c472864a5e35eee4f492fde6429c6`
- Task 97：`TASK97_REPOSITORY_LOCAL_COMPLETE`
- current main CI：GitHub Actions run `33305210601` success；build、governance、cross-domain、12-owner matrix均通過。
- 本次人工 Authority：允許 Anomalies repository-local source／tests／本任務專屬文件施工，並允許與 LINE 後端瘦身平行。
- 不授權：production／`union_db`、provider effect、deployment、entry switch、destructive DB cleanup、published migration rewrite。

若開始施工時 `main` 已超過上述 SHA，Agent 必須先 rebase／refresh current HEAD，確認 material drift；不得把本 SHA 當永久基線。

## 2. Task 97 已吸收且不得重做

Task 97 repository-local closeout 已確認下列方向，不得重新設計：

- `current_anomaly_issues` additive successor與 current-only projection方向。
- generic durable `anomaly.recheck`；不得建立 anomaly-specific claim／delivery history。
- predicate false直接刪 current row，不保存 resolved occurrence/history。
- owner mutation＋recheck intent、projection reconcile＋intent complete的 outer-UoW原則。
- external caller未知的 legacy public entry保留 typed 410，不做 physical delete。
- Access security-alert intent／Anomalies `system_alerts` projection的 current owner boundary。
- repository／route transaction、writer／entry governance的 Task 97 final classifications。

任何 Task 97 已 zero-reference retirement 的 internal implementation不得為了保留歷史而恢復。

## 3. Current-head refresh findings

### 3.1 Registry 已收斂為 15 current definitions

`domains/anomalies/registry.py::default_anomaly_registry()` current HEAD 只組合 15 個 current definitions：

- `SCHEDULE-006`
- `PAYOUT-002`
- `GOVSUB-001`～`GOVSUB-005`
- `GOVSUB-007`
- `IMPORT-003`
- `IMPORT-006`
- `BECLASS-001`
- `SCHEDULE-002`
- `SCHEDULE-003`
- `LINE-006`
- `LINE-004`

因此舊「43-code runtime registry」不再是 current施工 denominator。25 個 owner work items與3個 retire／merge項目只作
replacement／absence readback驗證，不得重新塞回 anomaly registry。

### 3.2 仍存在的 legacy compatibility 語意

current registry仍可看到舊架構 compatibility surface，例如：

- `AnomalyProjectionKind.FINANCE_OCCURRENCE`
- `AlertWorkflowStatus.OPEN / CLAIMED / RESOLVED`
- `CurrentAlertProjection`
- `claim_alert()`／`resolve_alert_workflow()`
- 舊 current-alert reducer／auto-resolution compatibility contract

這些名稱不代表一定全部可立即刪除；Agent 必須先做 exact caller／test／replacement scan。若只保護已退役
occurrence／claim／resolve語意且 current caller=0，應以 current-only successor取代後移除，不建立 legacy alias。

### 3.3 Manual action readiness仍需逐碼 current 驗證

例如 current `BECLASS-001` definition仍沒有 `available_actions`。所有 15 codes 必須依 current正式規格逐碼驗證：

- closed subject identity
- owner predicate／owner snapshot token
- manual Query → Preview → Apply → fresh readback
- completion predicate
- durable recheck intent
- redacted public details

缺項只阻擋該 code lane，不授權 generic resolve或 raw mutation。

## 4. Current execution packages

### ANM-P1：15-code current contract closure

只盤點／修正 current 15 definitions、typed details、subject identity、manual action descriptors、owner-lock與recheck mapping。

- 13 個非 LINE codes可獨立施工。
- `LINE-004`／`LINE-006` 的 LINE owner query/action implementation由平行 LINE Agent擁有；Anomalies Agent只擁有 detector／projection／typed descriptor消費端。
- 若 LINE peer尚未提供必要 typed contract，標 `WAIT_PEER_LINE_CONTRACT`，繼續其他 codes，不得修改 LINE source。

### ANM-P2：legacy application semantics shrink

對 Anomalies 自有 Domain／Subsystem／API／repository 做 exact zero-reference cleanup：

- occurrence／claim／resolve／timeline compatibility
- obsolete recovery／legacy projector semantics
- 只服務已退役語意的 tests

保留：current issue、public typed 410、owner boundary、rollback、current projection、zero-reference oracle tests。

### ANM-P3：current API／React contract closure

只把 `#anomalies` 與 API 收斂到 15 current issues、closed typed details、owner actions與 live best-effort pagination。
25 owner work items必須留在 owner頁面／owner query，不建立跨 Domain mega-query。

### ANM-P4：repository-local closeout

跑 Anomalies canonical root、affected cross-domain、build／governance／12-owner preflight、full non-engine Python與React affected gates。
DB 1016 engine若無合法 `lu_test_*` 環境維持 `DEFERRED_DB_ACCEPTANCE`，不阻止 repository-local task closeout。

## 5. Parallel write set — Anomalies Agent 專屬

可修改：

- `domains/anomalies/**`
- `subsystems/anomalies/**`
- `infrastructure/mysql/*anomaly*`
- 明確 Anomalies source adapters，且不得改 owning Domain root mutation
- `api/routes/anomaly*`
- `api/dependencies/anomaly*`
- `api/schemas/anomaly*`
- `tests/domains/anomalies/**`
- Anomalies-specific higher-boundary tests
- React Anomalies page/client/typed adapters（只限 anomaly surface）
- 本 Anomalies execution SSOT／Anomalies專屬 receipt

禁止修改 LINE peer write set：

- `domains/line/**`
- `subsystems/line/**`
- `infrastructure/line/**`
- `infrastructure/mysql/line_*`
- `api/routes/line_*`
- `api/dependencies/line_*`
- `api/schemas/line_*`
- `line/**`
- LINE canonical tests

## 6. Shared hot spots — 兩個 Agent 都不得直接寫

下列路徑只由最後 integration writer收斂，兩個平行 Agent都不得修改：

- root `README.md`
- `document/功能開發計畫/README.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- Task 97 entry／writer／production-script／commit artifacts與其 generators
- `.arch-map/index.md`、`.arch-map/meta.yaml`
- `.github/workflows/**`
- `api/main.py`
- generic `subsystems/jobs/**` 與 shared durable-job framework
- `db/schema_parts/**`、migration／release／fresh assembly

需要 shared hot spot變更時，Agent只在 receipt列出 `INTEGRATION_WRITER_FOLLOWUP`，不得自行修改。

## 7. Cross-task boundary

LINE peer負責 LINE owner side：identity、binding、delivery、configuration、provider retry、LINE-specific typed query/action。
Anomalies負責 LINE-004／006 的 current issue predicate projection與 action descriptor consumer。

禁止：

- Anomalies Agent直接修 LINE binding／delivery root。
- LINE Agent直接改 anomaly registry、current projection或 anomaly API。
- 任一 Agent為了跨任務方便建立 shared raw dict、generic mutation、compatibility wrapper。

若需要對方新 contract，使用 `WAIT_PEER_*`，先完成不相依的 slice；兩支 branch merge後再做一個小 integration slice。

## 8. Completion

Repository-local完成需同時滿足：

- 15-code current contract逐碼有 terminal result；允許 `WAIT_PEER_LINE_CONTRACT` 只作中間狀態，不可作最終完成。
- legacy anomaly-owned application semantics有 exact keep／rewrite／delete disposition。
- current API／React只表達 current issues。
- Anomalies canonical tests、affected cross-domain、build／governance、12-owner matrix通過。
- shared hot spot follow-up已由 integration writer收斂。

DB／production／external acceptance保持獨立 deferred，不得偽裝PASS。

```text
ANOMALIES_PARALLEL_EXECUTION_READY
DESTRUCTIVE_CUTOVER_NOT_AUTHORIZED
```
