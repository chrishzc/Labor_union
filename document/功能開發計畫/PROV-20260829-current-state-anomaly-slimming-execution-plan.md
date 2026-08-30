---
doc_type: execution-plan
declared_status: blocked
date: 2026-08-29
owner: anomalies / architecture-governance / owning-domains
task_level: T3
base_ref: eaca24903197400343e72342e5f03970e0fda078
execution_authority: planning / read-only inventory only
---

# Current-state 異常機制瘦身完整執行計劃

> Current status owner是`PROV-20260830-current-state-anomaly-task97-authority-reconciliation.md`：
> Task 97 repository-local prerequisite已完成；本計畫仍`NOT_READY`且等待另行授權的current-head bounded
> refresh。下文舊base對`UNAVAILABLE_IN_BASE`／`blocked_by_task97_priority`的敘述只作historical provenance。

## 0. Current readiness、Authority 與禁止效果

本計劃目前固定為 `SPEC_GAP / NOT_READY`。第 1 節的八項人工裁決仍是產品方向
Authority，但不構成 source replacement、刪檔、API cutover、entry retirement、schema 或 DB migration
的執行 Authority。在本節的重新收旂 gate 全部通過前，Agent 只能修正 current SSOT、本計劃與
執行唯讀 inventory；不得修改 production code、schema、migration、API、React、worker wiring
或 entry-point disposition。

重新收旂必須同時滿足：

1. 15 個 current issue 都有 terminal-ready 的 owner action contract；不得用 generic resolve、
   navigation-only 或「尚未支援」代替。
2. 25 個 owner work item／validation result 都有 typed Query、owner UI、completion predicate 與
   replacement readback，且不出現在 `#anomalies`。
3. public issue identity、API、bounded recheck concurrency、Task 97 final-artifact refresh、current dependency inventory 與
   destructive rollback contract 均完成本計劃規定的 gate。
4. 唯有 automation 能保留 `blocked_capability`；manual action 或 owner replacement 任一缺漏時，
   整體 API／DB／entry cutover 固定不得開始。
5. read-only review、strict UTF-8、治理 validator 與 reference scan 全部 PASS 後，才可依
   2026-08-29 人工條件式授權，將 `declared_status` 恢復為 `approved`，並恢復原本僅限
   source、tests、disposable DB 與 allowlisted `lu_test_*` 的 Authority。

```yaml
spec_route:
  status: SPEC_GAP
convergence:
  status: NOT_READY
  blockers:
    - 15-code owner action source map incomplete
    - 25 owner replacements incomplete
    - 15-code subject scalar normalization and public redaction views incomplete
    - recheck owner-lock and maintenance subject-universe mappings incomplete
    - Task 97 canonical dependency unavailable in base
    - dependency inventory lacks executable successor gates
    - destructive migration target, backup implementation and authority incomplete
```

## 1. 目的與最新人工裁決

本計劃把目前 Anomalies 的「歷史事件、追蹤狀態機、必要性移轉、current projection」四套機制，
收斂為一個只表達**當下仍成立問題**的 current-state projection。

最新人工裁決固定為：

1. 異常不是需要永久保存的歷史事件。
2. 每個 owner 狀態改變後重新檢查 predicate；predicate 不成立時，current issue 直接刪除。
3. 人工 claim、人工 resolve、tracking close 都不能取代 owner root 修正，也不需要保留為另一套異常歷史。
4. 需要判斷的問題直接提供 owning Domain 的人工處理入口，例如 HCM 訂單與 BeClass 表單無法唯一配對。
5. 格式錯誤優先由 LIFF／後端輸入驗證阻止；既有或歷史資料才進 owner 人工核查，不升級為永久 anomaly occurrence。
6. 只有結果唯一且安全的流程才自動化，例如已驗證 recipient 的補資料通知、可重播的 LINE retry、可證明等價的匯入重算。
7. 自動化所需能力尚未存在時，該 automation slice 標成 `blocked_capability` 並跳過；不得建立假按鈕、假成功、generic root editor 或 provisional SQL writer。
8. 異常頁只能呼叫 API／Application／Domain typed boundary，不得直接讀寫 DB 或旁路既有架構。

這項裁決取代原 `06_Anomalies_Domain.md` 的 immutable occurrence、workflow history、
reclassification disposition 長期保存要求，因此屬 T3 owner／SSOT／schema／public contract 變更。
本計劃目前只允許先修正 current SSOT 與完成唯讀 inventory；第 0 節重新收旂前，不得開始
production code、API cutover、source replacement、刪檔或 migration。production、`union_db`、外部
provider、deployment、entry switch 與實際 configured DB destructive cleanup 仍須依精確 target
與 DB gate 另行取得 Authority。

## 2. 範圍與非目標

### 2.1 本計劃涵蓋

- 43 個現有 anomaly definition 的逐碼 disposition。
- current issue detector、bounded recheck、projection reconciliation 與刪除語意。
- owner work queue、輸入驗證、人工 Preview／Apply 入口及少量 automation 的責任重分配。
- Anomalies registry、Domain／Subsystem、MySQL adapter、API、React 與 worker cutover。
- anomaly-owned history／tracking／reclassification schema 的停止寫入、資料處置及最終退役。
- entry-point queue、README、正式索引、Task 96 current register 與相關測試收斂。

### 2.2 本計劃不涵蓋

- 改寫 Orders、Scheduling、Finance、LINE 等 owning Domain 的正式金額、日期或 lifecycle 規則。
- 用 anomaly status 代替 owner root、receipt、payment、allocation、assignment 或 binding 事實。
- production／`union_db` migration、entry switch、外部 LINE provider 操作或不可逆部署。
- 為未完成能力製造暫時性 direct DB、raw endpoint、browser-local 假資料或 generic status editor。
- 刪除 owner Domain 因法規、財務或正式業務需要保存的 immutable payment／allocation／correction receipt；
  本計劃只移除「異常自己另外保存的一套歷史」。

## 3. Current baseline 比對結果

### 3.1 Repository identity

- Local branch：`main`
- Local HEAD：`eaca24903197400343e72342e5f03970e0fda078`
- GitHub `chrishzc/Labor_union` default branch：`main`
- GitHub 最新 commit：同一個 `eaca24903197400343e72342e5f03970e0fda078`
- 原盤點開始時 worktree：clean；本計劃修復時已有大量使用者 dirty／untracked paths，
  此行不再可作為施工 baseline。每次 read-only review 必須重新記錄實際狀態。

### 3.2 Registry 現況

`default_anomaly_registry()` 現在共有 43 碼：

| lifecycle | 數量 | 現況 |
|---|---:|---|
| `active` | 34 | 仍進異常中心 |
| `work_item` | 7 | 已開始移出異常，但仍留在完整 anomaly catalog |
| `retired` | 1 | `SCHEDULE-005` |
| `audit_only` | 1 | `staff_payout_overpayment` |

現行規格 §16 仍寫 42-code audit 與 33 active 目標；後來加入
`HISTORICAL-BASELINE-ROOTS-001` 後，live registry 已變為 43 catalog／34 active。

### 3.3 底層機制現況與目標差異

| 邊界 | Current live 行為 | 本計劃目標 |
|---|---|---|
| current alert | predicate false 後把 row 改為 `predicate_active=0`、`workflow_status=resolved` | predicate false 後刪除 current row |
| 人工進度 | `open → claimed → resolved`，另寫 immutable workflow event | 無 anomaly claim／resolve 狀態機；多人衝突由 owner version／Preview／Apply 控制 |
| 財務異常 | `finance_anomaly_occurrences` 永久保存 occurrence | 財務事實留在 Finance owner；Anomalies 只保留當下 issue |
| 匯入警示 | occurrence＋六狀態 tracking＋receipt＋outbox＋resubmission association | 格式問題留在該次匯入結果；需處理者成為 owner current review/work item，完成後消失 |
| 必要性 migration | immutable reclassification disposition／receipt／batch | 不再為「從異常移到待辦」另造 anomaly history；切換後由 owner Query 直接讀取 |
| 歷史 baseline | v1＋v2 occurrence、membership、successor、delivery、checkpoint、readback | 移除 umbrella anomaly；逐一顯示真正 owner 缺根工作項 |
| API detail | 回 occurrence timeline、workflow timeline、claimed/resolved 狀態 | 回 current predicate、owner evidence、blocking effect、人工 action 與 capability status |
| React | 有「已認領／已解決」、累計偵測次數與 timeline | 只顯示現在仍存在的問題及可執行 owner action |

六個 anomaly/history schema parts 目前合計建立 25 張專用表：

- `113_anomaly_registry_projection.sql`：4 張；
- `127_anomaly_root_fact_projector.sql`：2 張；
- `195_import_warning_tracking.sql`：6 張；
- `1009_anomaly_reclassification_disposition.sql`：3 張；
- `1011_historical_baseline_projector.sql`：4 張；
- `1014_historical_baseline_projector_v2.sql`：6 張。

Static reference scan 精確找到 99 個 API／Subsystem／Infrastructure／React／test 檔直接引用這些 table family。
entry-point queue 有 25 個 anomaly／import-warning 相關 entry，其中 7 個仍為 `review_required`。

這 25 張表與 99 個直接相依檔案不是「只停止使用即可」的保留清單。第 10 節目前只完成
path coverage；`99/99` 不代表已有可執行 successor、replacement readback 或 deletion gate。每列
補齊第 10.5 節的 terminal fields 前，只是 read-only inventory，不授權依以刪檔、rewrite 或退役。
最終每項只允許以下裁決：

- `delete`：責任只服務被退役的 occurrence／tracking／claim／resolve／reclassification／baseline 機制；
- `rewrite`：仍承載 current issue 行為，但必須改接新 registry、recheck、storage 或 typed view；
- `keep-owner`：檔案或資料屬 owning Domain 正式 root／event／receipt，而不是 anomaly history。

不得使用 `keep-compatibility`、`archive-in-source`、`unused-for-now` 或無 owner 的 `defer`。找不到合法
current caller、owner 或驗收情境的檔案固定刪除；舊測試若只保護已退役語意，必須刪除並以新契約測試
取代，不能改名為 legacy test 繼續累積。

### 3.4 必須刪除的錯誤假設

- `resolve` 不代表修復完成。
- `claim` 不應成為處理門禁。
- 曾經出現過異常，不需要讓 Anomalies 永久保留一份 occurrence。
- code 從 anomaly 改成 owner work item，不需要 immutable reclassification event。
- 同一問題再次出現時，只需重新建立 current row，不需要 reopen history。
- API 成功、通知送出、job succeeded、欄位非空都不能直接代表 owner predicate 已解除。
- 不能因為要刪歷史機制，就連 owner Domain 的合法付款、配對、匯入或 correction evidence 一併刪除。

## 4. Target architecture

### 4.1 唯一模型

Anomalies 最終只保留：

```text
Owner root facts
  → owner predicate / typed detector
  → bounded RecheckScope
  → CurrentIssueReconciler
  → current_anomaly_issues（只含目前 active rows）
  → bounded typed API
  → React 異常頁
  → owning Domain Query / Preview / Apply
  → owner root 改變
  → post-commit recheck
  → predicate false 時 DELETE current issue
```

### 4.2 Core typed contract

下列名稱與語意是 public／persistence contract，不得由執行 Agent 微調：

```text
RecheckScope
- owner_domain
- definition_codes
- subject_type
- subject_ids（canonical sorted unique）
- scope_snapshot_token
- cursor

CurrentIssueCandidate
- definition_code
- owner_domain
- subject_identity
- owner_version
- severity
- blocking
- typed_details
- manual_actions
- automation_status

CurrentIssueProjection
- issue_key
- definition_code
- owner_domain
- subject_identity
- owner_version
- severity
- blocking
- typed_details_contract
- episode_started_at
- last_verified_at
- current display data（closed typed details）

RecheckResult
- authoritative_complete
- candidates
- next_cursor
- owner_snapshot_token
```

Public identity 固定為：

1. `subject_identity` 是每個 definition code 的 closed typed object；欄位名、型別、normalization 與
   compound ordering 必須在 15-code source map 逐碼完整定義。
2. `issue_key` 是去敏且穩定的 opaque key：`ci_` 加上對
   `{"v":1,"definition_code":...,"subject_identity":...}` 的 UTF-8、sorted-key、compact JSON，
   使用專用且可注入測試的 `issue_identity_key_v1` 取 HMAC-SHA-256 lowercase hex。
   不得使用可對低熵 case／batch identity 離線枚舉的無密鑰 digest。API 不回傳
   raw `subject_identity`、HMAC input 或 key version；只回各 code 的 closed redacted subject view。
   key 缺失或版本不可用時 fail closed，不得改用裸 hash。
3. 2026-08-29 人工裁決：同一 canonical `definition_code + subject_identity` 跨多次
   episode 永遠使用同一 `issue_key`。一般 key rotation 不得改變已定義 identity；
   需更換 identity key 時必須另有保留公開 key 穩定性的 exact migration contract 與 Authority。
   重新 insert 仍必須產生新
   `episode_started_at`；`last_verified_at` 只表示本次 current episode 最後完整重查。row
   刪除後兩者不另行保存。
4. details discriminator 固定為 `definition_code`，contract version 固定從 `1` 開始；未知
   code、version、缺欄或額外欄位回 `anomaly_projection_data_integrity_violation`。
5. `GET /api/v1/anomalies` 只允許 `definition_code`、`owner_domain`、`blocking`、`limit`、
   `cursor` filter。`limit` 預設 50、上限 100；排序固定為 blocking 優先、severity
   由高到低、`episode_started_at` 舊到新、`issue_key` ascending。cursor 是有 version、
   不可竄改的 opaque token，必須綁定相同 filters、limit 與最後排序 tuple；malformed、
   簽章錯誤、版本不支援或 binding 不符回 typed `anomaly_cursor_invalid`。
   2026-08-29 人工裁決為 live best-effort pagination：cursor 不綁 snapshot，每頁都讀取
   當下 current rows；翻頁期間的 insert、delete 或排序欄位變動可造成跨頁漏列或重複。
   client 應以 `issue_key` 去重，需最新 authoritative current view 時必須從第一頁重新查詢；
   UI 不得將一次翻頁結果表示為 snapshot-complete。
6. detail route 固定為 `GET /api/v1/anomalies/{issue_key}`。manual action 只回 closed owner
   action descriptor，React drawer 再呼叫該 owner 的 Query／Preview／Apply；Anomalies API 不接受
   generic mutation payload。

### 4.3 Recheck 不變量

1. 先建立 canonical bounded `RecheckScope`，精確列出 definition codes、subject type 與
   canonical sorted unique subject IDs。Event path 只含受影響 subject；maintenance path 使用
   deterministic bounded cursor。
2. 每個 definition 必須將 subject 映射為 closed `owner_lock_keys`；每個 key 固定為
   `(owner_domain, owner_root_type, canonical_owner_root_id)`。Application 依該 tuple 的 canonical
   UTF-8 byte ordering 取得 owner／scope lock；指向同一 owner root 的不同 code／subject type
   必須產生相同 lock key。映射不完整固定 `SPEC_GAP`。不得以「鎖現有
   current row」取代，因為 row 不存在時無法防止 stale insert。
3. Owner facts 必須在取得 lock 後讀取，並產生能覆蓋整個 scope 的 monotonic owner
   version 或 snapshot token。無法產生 token 的 scope 固定 `SPEC_GAP`，不得施工。
4. Detector 只使用該 snapshot 計算完整 candidate set，並明確回報
   `authoritative_complete`。incomplete、timeout、schema drift 或 owner unavailable 固定整批零寫入、
   零刪除。
5. 寫入前在同一 outer transaction 重新驗證 owner version／snapshot token；已過期時
   整批零寫入，不得局部 upsert 或 delete。
6. token 仍 current 且 scope 完整時，才在同一 outer transaction 內對精確 scope
   執行 present upsert、absent delete，然後一次 commit。Repository 不得 commit／rollback；route、
   worker、detector 不得直接寫 current table。
7. 重疊 scope 使用完全相同的 lock ordering 與 token validation。duplicate candidate、重複
   subject 或 non-canonical ordering 固定 fail closed，不得以 unique-key retry 掩蓋。
8. 每個會改變 owner root 的 transaction 必須在同一 commit 寫入通用 durable recheck intent。
   intent append 本身失敗屬 owner transaction failure，整個 owner mutation 零提交；只有 intent
   已與 owner root 一起 committed 後的處理失敗、結果不明或 worker 中斷，才不回滾
   owner transaction，並保留可重播 intent。
9. bounded maintenance repair 的 subject universe 必須是「owner 可枚舉的 candidate-relevant
   subjects」與「current projection 已有 subjects」的 canonical union，分別使用 deterministic
   bounded cursor／watermark 後合併去重。只掃其中一側不得宣稱 complete；無法取得任一側
   authoritative page 時固定零 delete。
10. repair 不從舊 alert snapshot 復原、不建立 occurrence／tracking／reclassification history。
   false predicate 直接 delete current row；同一 issue 再次成立時重新 insert current episode，無
   reopen／replacement history。
11. current issue details 必須是 closed typed union；raw `dict` 不得穿過 API client 或
    render function。通知、provider retry 等副作用由 owner outbox／durable job 負責，不由
    current issue table 驅動或保存歷史。

### 4.4 人工與自動處理

- 每個保留的 current issue 至少有一個 terminal-ready owner-specific 人工入口；明確安全
  blocker 可解釋為何不可 Apply，但不能取代人工入口。
- 人工入口固定為 owner Query → Preview → Confirm → Apply → fresh readback → recheck。
- UI 不顯示 generic resolve、任意 target status、任意 endpoint 或 raw SQL 欄位。
- Automation 是 action 的可選附加能力，不是 current issue 的生命週期。
- Automation 未完成時回 `not_available`／`blocked_capability`；manual action 仍可用。
- 如果連人工入口都不存在，producer 不得以「尚未支援」的無操作警報冒充完成，
  該 code lane 與整體 cutover 均保持 `SPEC_GAP`。

## 5. 43-code 最終 disposition matrix

最終 runtime anomaly registry 只保留下表標成「current issue」的 15 碼；25 碼改由 owner typed Query
直接提供工作項／驗證結果；3 碼退役或合併。舊碼不得為了解碼 anomaly history 而永久留在 runtime catalog。

| Code | Current | Target | Owner 行為／完成條件 | Automation |
|---|---|---|---|---|
| `SCHEDULE-006` | active | current issue | Scheduling 人工修正 official service dates／coverage；重新符合合約範圍後消失 | 不先做 |
| `PAYOUT-001` | active | owner work item | Staff Payables 到期付款清單；balance=0 後從清單消失 | 不需要 |
| `PAYOUT-002` | active | current issue | 到期後義務變動，由 Staff Payables 人工確認差額與處置；一致後消失 | 不先做 |
| `PAYOUT-003` | active | owner work item | Staff 主資料／Staff Payables 銀行帳戶維護；唯一有效帳戶成立後解除付款 blocker | 不需要 |
| `GOVSUB-001` | active | current issue | 人工選定唯一補助批次；配對成立後消失 | 不先做 |
| `GOVSUB-002` | active | current issue | 人工分攤至 item 且金額守恆；完成後消失 | 不先做 |
| `GOVSUB-003` | active | current issue | 修正補助 batch／allocation／ledger 完整性；fresh integrity clear 後消失 | 僅安全 rebuild 可做 |
| `GOVSUB-004` | active | current issue | 人工選定合法 reversal target／amount；合法 linkage 後消失 | 不先做 |
| `GOVSUB-005` | active | current issue | 人工處理 frozen claim 與正式服務事實 drift；一致或合法 revision 後消失 | 不先做 |
| `GOVSUB-006` | active | owner work item | Government Subsidy 處置佇列選 offset／return；disposition committed 後移除 | 不需要 |
| `GOVSUB-007` | active | current issue | 超額政府退款阻擋，人工裁決；合法 payable／allocation 後消失 | 禁止自動 |
| `client_over_refund_recovery_open` | active | owner work item | Client Finance 追收清單；remaining=0 後消失 | 不需要 |
| `client_refund_underpayment` | active | owner work item | Client Finance 顯示退款 remaining；結清後消失 | 不需要 |
| `staff_overpayment_recovery_open` | active | owner work item | Staff Payables 追收清單；remaining=0 後消失 | 不需要 |
| `staff_payout_underpayment` | active | owner work item | Staff Payables 顯示剩餘應付；結清後消失 | 不需要 |
| `staff_payout_overpayment` | audit_only | merge／remove | 不保留第二個 anomaly；由 staff recovery owner work item 表達當前追收 | 不需要 |
| `IMPORT-001` | active | input validation／owner review | 新資料由 LIFF＋backend 驗證拒絕；歷史資料在 Case Import review 修正後消失 | 不需要 |
| `IMPORT-003` | active | current issue | Client BeClass 已存在但沒有 HCM counterpart；只有 owner 驗證後形成唯一、一致、可追溯 accepted mapping 才消失 | 補資料通知能力完成後才做 |
| `finance_import_manual_review` | finance occurrence | owner work item | Finance Import 未分類銀行列 review queue；正式分類／posting 後移除 | 不先做 |
| `CLIENTREFUND-001` | finance occurrence | owner work item | Finance Import／Client Finance 退款退匯分類與重開義務；完成後移除 | 不先做 |
| `IMPORT-006` | active | current issue | Finance Import 批次完整性矛盾；完整一致後消失 | 僅 deterministic replay/rebuild |
| `IMPORT-004` | active | input validation／owner review | HCM 欄位問題留在匯入結果；修正來源或人工裁決後移除 | 不需要 |
| `HISTORICAL-ORDER-001` | active | owner work item | Orders 歷史匯入人工核查；裁決寫回 owner 後移除 | 不需要 |
| `HISTORICAL-BASELINE-ROOTS-001` | active | retire | 刪除 umbrella；各缺根由實際 owner work item／current issue 表示 | 禁止重建 |
| `ORDER-001` | work_item | owner work item | Orders／Matching 顯示尚未發送資訊 1 | 不需要 |
| `ORDER-002` | work_item | owner work item | Orders／Matching 顯示已接受但尚未發送資訊 2 | 不需要 |
| `ORDER-003` | work_item | owner work item | Orders／Matching 顯示等待照服員回覆 | SLA 未裁決前不自動升級 |
| `ORDER-004` | work_item | owner work item | Orders／Matching 顯示等待客戶決定 | SLA 未裁決前不自動升級 |
| `BECLASS-001` | active | current issue | HCM 已存在但沒有唯一且一致的 Client BeClass counterpart；只有 owner 驗證後形成可追溯 accepted mapping 才消失 | verified LINE 補資料能力完成後才做 |
| `DOC-SEND-001` | work_item | owner work item | Document Delivery 待發履歷清單；成功送達後移除 | delivery task 自己處理 |
| `RECEIVABLE-001` | active | owner work item | Client Finance 催收清單；逾期餘額歸零後移除 | 可另做提醒，不是 anomaly |
| `CLIENTPAYABLE-001` | active | owner work item | Client Finance 退款付款清單；結清後移除 | 不需要 |
| `RETURN-001` | active | owner work item | Client Finance 補助退還付款清單；結清後移除 | 不需要 |
| `SUBSIDYADVANCE-001` | work_item | owner work item | Client Finance／Government Subsidy 墊付到期清單；完成後移除 | 不需要 |
| `SCHEDULE-001` | active | owner work item | Scheduling 假日服務決定清單；完成決定後移除 | 不需要 |
| `SCHEDULE-002` | active | current issue | replacement／substitution lineage 或必要 split 不完整；完整後消失 | 不先做 |
| `SCHEDULE-003` | active | current issue | 實際排班重疊；人工調整至無 overlap 後消失 | 不先做 |
| `SCHEDULE-005` | retired | retire | 偏好不是 hard anomaly；不得再產生 | 禁止重建 |
| `LINE-001` | active | owner work item | 只有 pending workflow 需要通知且 Client 未綁定時顯示 binding task | 不需要 |
| `LINE-005` | active | owner work item | 只有 pending workflow 需要通知且 Staff 未綁定時顯示 binding task | 不需要 |
| `LINE-006` | active | current issue | 只代表 terminal delivery／configuration failure；成功或設定修正後消失 | 安全 retry 可自動 |
| `LINE-002` | work_item | owner work item | LINE 等待回覆 task；回覆或 owner 結束等待後移除 | SLA 未裁決前不升級 |
| `LINE-004` | active | current issue | 同 subject type 多重有效 binding 或 projection 矛盾；修正後消失；client＋staff 雙角色合法 | 不先做 |

### 5.1 15-code owner action source map

每列 action contract 必須最終固定 typed Query／Preview／Apply、必要輸入、合法與禁止結果、
owner version／preview fingerprint、idempotency、receipt、fresh readback、completion predicate 與
`#anomalies` Drawer renderer。下表中任一 `SPEC_GAP` 都會阻擋整體 cutover；不得由 live
symbol 或舊 test 自動補成正式契約。

| Code | Owner／subject identity | Predicate／completion | Current contract evidence | Readiness |
|---|---|---|---|---|
| `SCHEDULE-006` | Scheduling；`case_no + generation` | official service dates／coverage 違反 owner oracle；修正後 clear | 只有 Preview candidate；Apply、receipt、readback 尚未在 owner spec 完整綁定 | `SPEC_GAP` |
| `PAYOUT-002` | Staff Payables；`obligation_identity + source_event_identity` | 到期後義務變動且差額未合法處置；owner 一致後 clear | live 僅 Query-style action；差額處置選項、Apply 與 terminal receipt 不完整 | `SPEC_GAP` |
| `GOVSUB-001` | Government Subsidy；`bank_fact_identity` | 無唯一合法 batch；accepted batch mapping 成立後 clear | 有 Preview candidate；Apply／readback 綁定尚未完整 | `SPEC_GAP` |
| `GOVSUB-002` | Government Subsidy；`bank_fact_identity + batch_id` | allocation 不唯一或不守恆；item allocation 守恆後 clear | 有 Preview candidate；Apply／receipt／negative outcomes 尚未完整 | `SPEC_GAP` |
| `GOVSUB-003` | Government Subsidy；`batch_id + integrity_revision` | batch／allocation／ledger integrity 矛盾；fresh integrity clear | live 僅 Query-style action；manual repair 與可選 deterministic rebuild 契約尚未完整 | `SPEC_GAP` |
| `GOVSUB-004` | Government Subsidy；`reversal_bank_fact_identity + source_receipt_id` | reversal target／amount 不合法；validated linkage 成立後 clear | 有 Preview candidate；Apply／receipt／readback 尚未完整 | `SPEC_GAP` |
| `GOVSUB-005` | Government Subsidy；`assignment_id + batch_id + claim_item_id` | frozen claim 與正式服務事實 drift；一致或合法 revision 後 clear | live 僅 Query-style action；legal revision command 與禁止結果尚未完整 | `SPEC_GAP` |
| `GOVSUB-007` | Government Subsidy；`payable_identity` | 政府退款實際超額；合法 payable／allocation 後 clear | 明確禁止自動，但 owner-specific 人工 Q／P／A 尚未定義 | `SPEC_GAP` |
| `IMPORT-003` | Case Import；`entity_kind + review_item_id` | Client BeClass 已存在但無 HCM；validated accepted mapping 成立後 clear | 不得任意選 candidate；evidence-verification Q／P／A 尚未完整 | `SPEC_GAP` |
| `BECLASS-001` | Case Import／Orders；`case_no` | HCM 已存在但無唯一一致 Client BeClass；validated accepted mapping 成立後 clear | 不得任意選 candidate；evidence-verification Q／P／A 尚未完整 | `SPEC_GAP` |
| `IMPORT-006` | Finance Import；`batch_id` | batch integrity 矛盾；owner readback 完整一致後 clear | 舊 `RetryAnomalyProjector` 不是 remediation；owner repair／deterministic rebuild contract 尚未完整 | `SPEC_GAP` |
| `SCHEDULE-002` | Scheduling；`assignment_id` | replacement／substitution lineage 或必要 split 不完整；owner lineage complete | owner repair Q／P／A 尚未完整 | `SPEC_GAP` |
| `SCHEDULE-003` | Scheduling；canonical sorted `assignment_id_a + assignment_id_b` | effective assignment／official dates 實際 overlap；無 overlap 後 clear | owner reschedule／correction Q／P／A 尚未完整 | `SPEC_GAP` |
| `LINE-006` | LINE Delivery；`case_no + notification_reason` | terminal delivery／configuration failure；success 或設定修正後 clear | durable retry 能力需重驗；manual retry／configuration action contract 尚未完整 | `SPEC_GAP` |
| `LINE-004` | LINE Identity；`subject_type + line_user_id` | 同 subject type 多重 active binding 或 root／projection 矛盾；identity integrity clear | 雙角色合法；owner identity correction Q／P／A 尚未完整 | `SPEC_GAP` |

### 5.2 25-item owner replacement map

每項 replacement 必須存在於下表指定的 owner page，並提供 closed typed response、
completion predicate 與 fresh replacement readback。本輪只能從現行規格確認 owner 與業務結果；
exact Query symbol、response version、React entry 或 readback 未被 current owner spec 唯一定義者一律保持
`SPEC_GAP`。

| Codes／items | Owner page | Required typed result／completion | Readiness |
|---|---|---|---|
| `PAYOUT-001` | Staff Payables payment queue | due obligation、balance、bank readiness；`balance=0` | `SPEC_GAP` |
| `PAYOUT-003` | Staff master／Staff Payables bank maintenance | staff bank blocker 與 masked account state；唯一有效帳戶成立 | `SPEC_GAP` |
| `GOVSUB-006` | Government Subsidy disposition queue | overpayment、`offset|return` disposition；disposition committed | `SPEC_GAP` |
| `client_over_refund_recovery_open`、`client_refund_underpayment` | Client Finance recovery／refund queue | remaining、owner version、legal actions；`remaining=0` | `SPEC_GAP` |
| `staff_overpayment_recovery_open`、`staff_payout_underpayment` | Staff Payables recovery／remaining queue | remaining、owner version、legal actions；`remaining=0` | `SPEC_GAP` |
| `IMPORT-001` | Case Import validation／review result | field-level validation result；validated source 或 owner disposition | `SPEC_GAP` |
| `finance_import_manual_review` | Finance Import classification queue | canonical bank fact／candidates／posting result；classification／posting terminal | `SPEC_GAP` |
| `CLIENTREFUND-001` | Finance Import／Client Finance refund-return queue | returned transfer、refund obligation、reopen outcome；owner handling terminal | `SPEC_GAP` |
| `IMPORT-004` | HCM import result／review | HCM source validation issues；corrected source 或 legal disposition | `SPEC_GAP` |
| `HISTORICAL-ORDER-001` | Orders historical import review | review identity、masked case、issue codes；owner remediation terminal | `SPEC_GAP` |
| `ORDER-001`～`ORDER-004` | Orders／Matching work queue | current matching stage／next legal action；owner stage complete | `SPEC_GAP` |
| `DOC-SEND-001` | Document Delivery queue | required document、recipient readiness、delivery task；delivery terminal | `SPEC_GAP` |
| `RECEIVABLE-001` | Client Finance receivable queue | overdue obligations／remaining；balance zero | `SPEC_GAP` |
| `CLIENTPAYABLE-001` | Client Finance payable queue | refund payable／remaining；settled | `SPEC_GAP` |
| `RETURN-001` | Client Finance subsidy-return payable queue | return payable／remaining；settled | `SPEC_GAP` |
| `SUBSIDYADVANCE-001` | Client Finance／Government Subsidy advance queue | advance due facts／settlement state；owner completion | `SPEC_GAP` |
| `SCHEDULE-001` | Scheduling holiday decision queue | staff/date decision context；decision committed | `SPEC_GAP` |
| `LINE-001`、`LINE-005` | LINE Identity binding queue | pending owner workflow／subject binding readiness；valid binding 或 workflow no longer needs notification | `SPEC_GAP` |
| `LINE-002` | LINE task queue | waiting task、owner version、reply state；reply 或 owner ends wait | `SPEC_GAP` |

### 5.3 3-code retirement／merge gate

- `staff_payout_overpayment`：不保留 anomaly occurrence；必須先證明 Staff Payables recovery owner
  Query 是唯一 current representation。
- `HISTORICAL-BASELINE-ROOTS-001`：退役 umbrella；必須先證明每個缺根已由實際
  owner Query／current issue 承接。
- `SCHEDULE-005`：退役 false-positive producer；Staff preference 只能影響 matching order 與
  explanation。

三項 replacement／absence readback 全部通過前，不得刪 code、producer、UI mapping 或舊 row。

## 6. Execution packages

每個 package 開始時重新記錄 branch、HEAD、dirty paths；若 base drift，先重做 scope diff。
狀態只用 `pending | in_progress | blocked | completed` 供本計劃執行記錄；正式 current register 仍使用專案既有狀態集合。

### ANM-SLIM-00：凍結 baseline 與 authority

**Owner**：architecture-governance
**Dependencies**：無
**Write set**：本計劃、`06_Anomalies_Domain.md`、`15_正式規格索引與裁決總表.md`、必要 owner spec amendment
**不得修改**：production code、schema、migration、entry queue

任務：

1. 重新執行 registry inventory，證明 base 仍為 43／34／7／1／1。
2. 列出 25 張 anomaly/history tables、所有 writer、reader、API、worker、CLI、React caller 與 FK。
3. 把最新人工裁決寫入 current SSOT，明確 supersede：finance occurrence history、import warning tracking machine、reclassification disposition、historical baseline umbrella、claim／resolve workflow。
4. 在各 owner spec 只補 observable contract：owner predicate、manual action、completion condition、automation eligibility；不得複製整份本計劃。
5. 將 `96_Current_剩餘代辦任務總表.md` 的 `CUR-P0-ANOMALY-RECOVERY-01` 改為指向本計劃，移除仍要求「33 active＋所有 occurrence history」的舊 terminal wording。

Acceptance：

- current SSOT 不再要求 Anomalies 保存 occurrence／tracking／reclassification history；
- 43-code matrix 與 owner 規格無衝突；
- code 尚未改動；
- `git diff --check`、strict UTF-8、治理 validator PASS。

Safe stop：若任何 owner predicate、人工 action 或完成條件仍不唯一，標 `SPEC_GAP`，
只允許其他已唯一 lane 繼續規格收旂與 read-only inventory；任一 code 尚有 gap 時仍依
第 0 節阻擋所有 production implementation 與整體 cutover。

### ANM-SLIM-01：建立 current issue kernel

**Owner**：Anomalies Domain／Subsystem
**Dependencies**：ANM-SLIM-00 completed；global transaction slimming 已固定 outer UoW contract
**Write set**：`domains/anomalies/` 新 current-issue models、`subsystems/anomalies/` reconciler、focused tests
**Shared hot spots**：`domains/anomalies/registry.py` 只由 integration writer 修改

任務：

1. 建立只含 15 current issue definitions 的 registry；移除 lifecycle、audit-only、work-item catalog 與 finance-occurrence projection kind。
2. 建立 `RecheckScope`、typed candidate／projection／result 及 closed details union。
3. 實作 pure reconcile candidate builder：完整 scope 的 present set 決定 upsert／delete set。
4. 移除 `AlertWorkflowStatus`、`claim_alert`、`resolve_alert_workflow`、`auto_resolution_blocked` 與 rulebook whitelist。
5. 驗證 false predicate、同 scope 中候選消失、同 issue 再次出現、owner query incomplete、stale owner version、duplicate candidate。

Acceptance tests：

- active candidate 首次出現 → insert intent；
- candidate 更新 → CAS update intent；
- candidate 不再存在且 scope authoritative → delete intent；
- owner unavailable／incomplete → 零 delete；
- 同碼同 subject 重複 → fail closed；
- runtime registry 精確 15 碼，無 work-item／retired／audit-only catalog。

### ANM-SLIM-02：建立唯一 current storage 與 reconciler transaction

**Owner**：Anomalies Subsystem／MySQL adapter
**Dependencies**：ANM-SLIM-01；repository-owned commit 清理完成
**Write set**：new current issue repository、Application composition、focused repository tests
**不得做**：在 repository commit、直接 drop 舊 tables、先切 API

任務：

1. 設計 `current_anomaly_issues` 最小 schema，只保存 active row；不含 claimed／resolved、occurrence、timeline、replacement 或 history FK。
2. Application 在一個 outer UoW：lock scope → upsert present → delete absent → commit。
3. 建立 deterministic issue key、unique `(definition_code, subject_identity)`、owner version CAS、details contract version。
4. Event consumer 只送 `RecheckScope`；repository 不接受外部提供的 resolved flag。
5. 建立 bounded maintenance recheck，cursor 不得掃整庫後無界持鎖。

Acceptance：

- concurrent recheck 不產生 duplicate；
- incomplete scope 不誤刪；
- delete／upsert 同 transaction rollback；
- repository 無 commit／rollback；
- current table 無 inactive／resolved row。

### ANM-SLIM-03A：Case Import／Historical lane

**Owner**：Case Import／Orders
**Dependencies**：ANM-SLIM-01
**Write set**：case-import detector／review Query、historical-order owner work queue、tests

任務：

1. `IMPORT-001`、`IMPORT-004` 改成 upload/LIFF validation result 或 bounded owner review，不送 current issue reconciler。
2. `IMPORT-003`、`BECLASS-001` 依第 5 節的方向建立不同的 subject-bounded current
   predicate。人工 action 只能送 owner 驗證的 evidence／accepted-mapping command；不允許在
   異常頁任意挑選候選、merge roots、直接修改 mapping 或 root。
3. `HISTORICAL-ORDER-001` 改由 Orders review Query 顯示；完成裁決後 Query 不再回傳。
4. 移除 `HISTORICAL-BASELINE-ROOTS-001` producer；真正缺根改由 Orders／Scheduling／Finance／Staff Payables typed work items 表達。
5. LINE 補資料 automation 只建立 capability contract；verified recipient／template／reply intake 未完成時標 `blocked_capability`，不實作 provider effect。

Acceptance：新 LIFF／Web input 格式錯誤在 intake 422／review result 處結束；歷史錯誤可人工處理；HCM／BeClass 無唯一配對才進 current issue；配對成功後 row 被刪除。

### ANM-SLIM-03B：Orders／Scheduling lane

**Owner**：Orders／Scheduling／Document Delivery
**Dependencies**：ANM-SLIM-01
**Write set**：owner work-item queries、Scheduling predicates/actions、tests

任務：

1. `ORDER-001`～`004`、`DOC-SEND-001`、`SCHEDULE-001` 從 anomaly producer 移至 owner query。
2. `SCHEDULE-005` producer、registry、UI mapping 與 calendar anomaly deep-link 全面移除。
3. `SCHEDULE-002` predicate 只承認不完整 replacement／substitution lineage 或必要 Finance／Payroll split；合法 replacement 不產生 issue。
4. `SCHEDULE-003` 使用 effective assignment／official dates 判定實際 overlap。
5. `SCHEDULE-006` 重用 Scheduling 正式 coverage oracle；人工 Preview／Apply 後 recheck。

Acceptance：正常等待／正常 replacement／偏好不產生 issue；真 overlap、lineage 缺漏、coverage conflict 產生 issue；修正後刪除。

### ANM-SLIM-03C：LINE lane

**Owner**：LINE Identity／Delivery
**Dependencies**：ANM-SLIM-01
**Write set**：LINE owner queues、identity/delivery predicates、tests

任務：

1. `LINE-001`、`LINE-005` 改為只有 pending owner workflow 真正需要通知時才出現的 binding work items。
2. `LINE-002` 留在 LINE task Query；無 SLA 前不得升級 anomaly。
3. `LINE-004` 只檢查同 subject type 多重 active binding、root/projection mismatch、replacement/revocation 未完成；client＋staff 雙角色為合法。
4. `LINE-006` 只代表 terminal delivery／configuration failure；queued、running、retry_pending 不產生 issue。
5. 若現有 durable delivery retry 已滿足 idempotency／recipient／timeout 契約，接通自動 retry；否則保留 manual retry 並標 `blocked_capability`。

Acceptance：合法雙角色、一般等待、retry pending 都不出現在異常頁；terminal failure 出現且成功 retry／修正設定後刪除。

### ANM-SLIM-03D：Finance／Payables lane

**Owner**：Finance Import／Client Finance／Staff Payables
**Dependencies**：ANM-SLIM-01；outer UoW boundaries stable
**Write set**：owner work queues、`PAYOUT-002`／`IMPORT-006` detectors、tests

任務：

1. 將 `PAYOUT-001`、`PAYOUT-003`、client/staff recovery、underpayment、`RECEIVABLE-001`、`CLIENTPAYABLE-001`、`RETURN-001`、`CLIENTREFUND-001`、`finance_import_manual_review` 改由 owner queries 顯示。
2. `staff_payout_overpayment` 不建立第二個 current issue；staff recovery root 是唯一 current representation。
3. `PAYOUT-002` 保留 current issue，人工處理仍走 Staff Payables typed command。
4. `IMPORT-006` 只代表批次完整性矛盾，不包含一般待分類銀行列。
5. Finance owner 的 ledger、allocation、recovery、payout、refund events／receipts 維持既有正式權威；只移除 anomaly occurrence copy。

Acceptance：一般到期、remaining、追收、退匯 review 都只在 owner queue；真正 late-change／batch-integrity 問題進 current issue；owner 完成後 current issue 刪除。

### ANM-SLIM-03E：Government Subsidy lane

**Owner**：Government Subsidy
**Dependencies**：ANM-SLIM-01
**Write set**：GOVSUB predicates、owner disposition query/action、tests

任務：

1. 保留 `GOVSUB-001`～`005`、`007` 的 current predicate 與人工入口。
2. `GOVSUB-006` 改為 owner disposition work item；不再由 anomaly lifecycle 表達 pending review。
3. 每個 predicate 必須重用 Government Subsidy owner oracle，不得由 alert snapshot 重算金額。
4. `GOVSUB-003` 只有 deterministic、完整且可 rollback 的 rebuild 才可自動化；`GOVSUB-007` 明確禁止自動 disposition。

Acceptance：所有金額保持 owner 守恆；ambiguous／invalid 不自動猜；合法 allocation／reversal／revision 後 current issue 刪除。

### ANM-SLIM-04：API 與 React cutover

**Owner**：Anomalies API／React integration writer
**Dependencies**：ANM-SLIM-02、03A～03E 全部 terminal-ready；15 個 current issue manual
action contract 與 25 個 owner replacement 全部通過 readback gate
**Write set**：Anomalies API schemas/routes/dependencies、React clients/adapters/page/tests

任務：

1. `GET /api/v1/anomalies` 只回 current rows，移除 `active_only`、resolved／claimed filter 及 workflow fields。
2. Detail 回 current typed details、owner facts、blocking effect、manual actions、automation availability；移除 occurrence／workflow timeline。
3. 移除 claim／resolve endpoints 與 React buttons/tabs/KPI。
4. 匯入 warning tracking UI 改接 Case Import／Orders／Finance 各自 owner page 的 typed queues，
   移除六狀態 transition 表單與 receipt client；這些 queue 不得在 `#anomalies` 重新聚合。
5. 保留並重用 owner-specific recovery workbenches；Apply 後 reload owner result及 current issue list。
6. 對 15 個 current code 建 closed discriminated response union；未知 code／details version fail closed。
7. `#anomalies` 只顯示 15 個 current issue；Drawer 使用各 owner bounded typed client 取得
   action context 並執行 Preview／Apply。25 個 owner work item 只顯示於各自 owner page，不建立
   跨 Domain raw-dict mega-query。

Acceptance：

- UI 只看得到目前存在的 issue；
- 無「已認領／已解決／累計偵測次數／歷史 timeline」；
- action 成功但 recheck 失敗時，顯示「owner 操作已提交、目前狀態待重新查詢」，不得假稱 issue 已消失；
- schema mismatch、partial failure、stale response 不清空其他有效區塊；
- React focused tests、TypeScript、build、fresh Browser success／empty／error／stale PASS。

### ANM-SLIM-05：Schema、preserve-data cutover 與舊資料移除

**Owner**：Global Migration／Anomalies
**Dependencies**：ANM-SLIM-02～04 source ready；DB seven-gate package approved
**Write set**：new schema part、schema assembly、release chain、descriptor、migration tests、operator docs

Change inventory 必須分四類：

| 類型 | 內容 |
|---|---|
| schema-only | 新 `current_anomaly_issues`、indexes、constraints |
| system-seed | 無；registry 是 source code contract |
| business-row-backfill | 無；新 current rows 必須由 fresh owner recheck 重建，不可 copy 舊 alert snapshot |
| destructive | 清除並 drop anomaly-owned history／tracking／reclassification／baseline tables 及舊 `anomaly_current_alerts` |

Cutover 順序：

1. Static release、descriptor、read-only plan 完成。
2. 停止 anomaly/import-warning/historical-baseline legacy writers；證明 outbox backlog 已處置或明確不再需要。
3. 建立新 current table。
4. 對 15 碼逐 owner 執行 bounded fresh recheck，完全由 owner facts 重建 current rows。
5. 新舊讀取結果只做 bounded comparison；不得把舊 history 當新 SSOT。
6. API／worker 切到新 table，執行 readback與 rollback rehearsal。
7. 在精確 DB Authority 下刪除 legacy anomaly-owned rows、FK、triggers、tables；不得碰 owner Domain history。
8. 任何會 drop legacy table 的 preserve-data target，都必須在破壞性步驟前建立短期、
   加密、受控且可驗證的 source backup，固定 expiry 與 rollback owner。必須實際演練
   schema／data／source-version 一致還原；沒有 backup 或還原證據時固定
   `DB_CHANGE_NOT_READY`。rollback window 關閉後必須刪除 backup，不能轉成新的永久
   異常封存。
9. 更新 canonical fresh schema，使 fresh clone 從未建立 legacy anomaly history tables。

DB gates 必須依 `10_Global_保留資料Migration與Cutover_Subsystem.md` §9 逐項輸出：Scope、Change inventory、Static release、Descriptor、Read-only plan、Engine verification、Developer acceptance。任一 `BLOCKED`／`NOT_RUN` 時總結固定 `DB_CHANGE_NOT_READY`。

Engine acceptance：

- fresh bootstrap 只有新 current table；
- 上一支援版＋代表性 active/inactive/history rows 可 preserve-data upgrade；
- 新 current rows 由 owner recheck 決定；
- legacy history tables 最終不存在；
- migration replay、crash resume、rollback rehearsal、strict target guard PASS；
- 不執行 `union_db`、production、replacement、`--switch`，除非另有 exact target Authority。

### ANM-SLIM-06：Entry-point、worker、文件與 dead code retirement

**Owner**：integration writer
**Dependencies**：ANM-SLIM-04、05 cutover evidence
**Shared hot spots**：entry queue、`api/main.py`、README、`15`、`96`、release manifest 僅一位 writer

#### 06.1 Mandatory dependency disposition

本計劃第 10 節目前只證明 base scan 的 path coverage，不是可執行 disposition inventory。
下列欄位逐列補齊，並由 read-only review 證明 replacement 真實可讀前，任何 `delete`、
`rewrite` 或 entry retirement 都固定禁止。新命中必須由 integration writer 先補入第 10 節；
不能由 lane Agent 自行保留或刪除。每一列至少包含：

```text
path_or_table
current_symbols_or_objects
current_callers
current_owner
target_disposition: delete | rewrite | keep-owner
replacement
deletion_or_rewrite_gate
focused_tests
final_writer_or_reference_scan
```

裁決規則：

1. 只要檔案唯一用途是 anomaly workflow event、finance anomaly occurrence、import-warning tracking、
   reclassification migration 或 historical-baseline umbrella，完成 replacement 後整個檔案刪除。
2. 同一檔案若同時包含 current 能力與 legacy 能力，先將 current 能力搬到責任清楚的新模組，再刪除舊檔；
   不在原大檔內留下 `legacy_*`、deprecated branch、feature flag 或 dead function。
3. 測試依 observable behavior 裁決。只驗 claim／resolve／timeline／occurrence retention／reclassification
   receipt 的測試刪除；能重寫為 current recheck／delete semantics 的測試移至新 owner／Subsystem test。
4. schema part 作為已發布 migration artifact若依 release 規範不可改寫，僅可留在 versioned migration chain
   供舊版升級；它不得再被 fresh canonical assembly 建立，也不得被 production code、runtime query 或新測試
   當作 current contract。這是 migration provenance，不是應用層 compatibility code。
5. 沒有 production caller 不能單獨作為刪除證據；但完成 owner／replacement／entrypoint 裁決後，沒有合法
   caller 的 source 必須刪除，不能以「可能將來有用」保留。
6. 每個 `delete` 必須先精確確認 inbound references；每個 `rewrite` 必須在舊 symbol 刪除後通過 focused tests；
   每個 `keep-owner` 必須證明其 table／event／receipt 由 owning Domain 正式規格要求。

第 10 節當前是 `blocked_inventory_contract`。只有每列 terminal fields 完整且 review PASS 後，
才能升格為 execution inventory。後續 final receipt 只摘要實際 deleted／rewritten／kept
數量、base drift 與驗證結果，不把已刪 source 全文複製到另一份 archive。

逐項裁決：

**保留／改契約**

- `GET /api/v1/anomalies`
- `GET /api/v1/anomalies/{issue_key}`
- owner-specific Query／Preview／Apply routes
- 一個 authenticated bounded maintenance recheck entry，若 general job operations 已可承接則不新增 public route
- React `#anomalies`，但只顯示 current issues

**退役候選**

- `POST /api/v1/anomalies/{fingerprint}/claim`
- `POST /api/v1/anomalies/{fingerprint}/resolve`
- `/api/v1/admin/anomaly-necessity-migration/**`
- `/api/v1/import-warning-tracking/**`
- anomaly occurrence／timeline recovery response surface
- anomaly-specific dead-letter retry／supersede routes；若仍有必要，移至 general durable-job operations，不保留 anomaly history 語意
- `scripts/rebuild_beclass_import_anomalies.py`，由 bounded owner recheck 取代
- historical baseline v1／v2 projector entry與worker wiring

每個 entry 依 `19_Global_Entry_Point_Governance.md` 執行 caller inventory、replacement readback、focused regression、rollback。HTTP 先 `retired_410` 或直接 removed 必須依外部 caller 裁決，不得只因 static caller 為零就刪。

文件更新：

- `README.md`：異常中心改為 current-only，移除 incident/anomaly/audit-retention worker 的錯誤描述。
- `00_開發者與Agent導覽.md`：更新 Anomalies 定位。
- `06_Anomalies_Domain.md`：只保留 current issue contract。
- `15_正式規格索引與裁決總表.md`：以新 43-code disposition 取代 42→33 migration snapshot。
- `22_銀行流水匯入與帳務異常處理正式規格.md`：Finance owner queue／current issue 分界。
- `96_Current_剩餘代辦任務總表.md`：只保留 current status、blocker、next gate。
- entrypoint queue：重新生成後逐項保留既有人工裁決，不得覆蓋成 `review_required`。

### ANM-SLIM-07：Final proof

**Dependencies**：ANM-SLIM-00～06 completed
**禁止**：在 focused failures 尚未分類前直接跑 full suite 掩蓋問題

驗證順序：

1. Static：registry 15-code exact set、legacy symbol/table/route writer scan、strict typed schema、UTF-8、`git diff --check`。
2. Module：15 predicates、25 owner queue/validation mappings、3 retire/merge mappings。
3. Subsystem：bounded recheck、scope completeness、upsert/delete atomicity、stale／concurrency／rollback。
4. Domain：各 owner manual action與 completion predicate。
5. API：current list/detail、owner action、removed workflow fields、typed errors。
6. React：`#anomalies` current-only page、Drawer owner actions、25 個 work queue 各自 owner page、
   no history UI、partial failure／stale suppression。
7. MySQL：fresh、preserve-data candidate、replay、crash resume、legacy tables absent。
8. Browser：每個分類至少一個 positive、empty、修正後消失、owner action failure 保留 issue。
9. Entry validator、writer inventory、dependency scan。
10. 最後才跑 Python full suite、React full suite、build、lint 與 Global smoke。

Final proof 必須同時滿足：

- runtime registry 精確 15 current issue codes；
- 25 碼只從 owner Query／validation result 讀取；
- 3 碼無 producer／runtime catalog／UI mapping；
- current predicate false 後 DB row 實際不存在；
- 無 anomaly claim／resolve／occurrence／tracking／reclassification writer；
- fresh canonical schema 無 legacy anomaly history tables；
- public API／React 無 raw dict、history timeline、claimed/resolved surface；
- owner Domain 正式 events／receipts 未受破壞；
- 25 張 legacy runtime 專用表全部為 `delete`；僅不可改寫的已發布 schema-part 檔可作
  `keep-owner(Global Migration provenance)`，runtime schema 與 production source 對這 25 張表為零引用；
- 99 個初始直接相依檔案及重掃新增命中全部取得 `delete | rewrite | keep-owner` terminal disposition，
  不存在 orphan module、無 caller compatibility、舊 API schema、舊 React client、舊 fixture 或只保護退役
  語意的測試；
- 所有必要 tests／DB gates／Browser gates 為 PASS，否則不得宣稱完成。

## 7. 與既有全域架構瘦身計劃的協作方式

本計劃目前不得以本機 untracked 的 Task 97 文件作為 formal dependency、receipt 或
terminal evidence。在目前 base HEAD 中 Task 97 固定為 `UNAVAILABLE_IN_BASE`；只有當正式
tracked artifact 可讀且能精確綁定 identity、revision、WP、receipt 與 terminal gate 後，才能替換
下表的抽象依賴。在此之前，只能執行本計劃明列的 read-only inventory 與 current SSOT
修正，不得開始 ANM-SLIM-01～07。

2026-08-29 最新人工優先序裁決：若本計劃與本機當前 Task 97 在 public contract、
owner／SSOT、transaction、writer、entry disposition、shared write set 或驗收基線發生衝突，
一律以 Task 97 優先，本計劃對該重疊 lane 立即停止寫入並標記
`blocked_by_task97_priority`。這個執行優先序來自 latest user Authority，不會將 untracked Task 97
自動升格為本計劃的 canonical dependency、completion receipt 或 terminal evidence。

取得正式 Task 97 後，本計劃才可依共享 hot spot 分流：

| 可平行 | 必須等待／單一 writer |
|---|---|
| ANM-SLIM-00 規格、43-code inventory、owner predicate盤點 | `registry.py`、`api/main.py`、schema assembly／manifest、entry queue、README／正式索引 |
| 03A～03E 各 owner pure predicate／Query 設計與測試 | 新 reconciler transaction 必須等待 repository-owned commit／route-owned transaction 收斂 |
| React typed schema草稿與 fixture盤點 | `AnomaliesPage.tsx` final cutover由單一 integration writer |
| 舊 API／table caller read-only inventory | writer inventory與entrypoint queue只在兩邊 source穩定後生成一次 |

與原八項全域計劃的 dependency：

1. `clients.py` direct mutation、repository commit、route transaction 尚在改時，ANM-SLIM-02 不施工。
2. bounded typed Query 工作可與 ANM-SLIM-04 合併驗收，不建立第二套 raw dict compatibility。
3. writer inventory 與 entry-point queue 不在 anomaly lane 提前定稿，交由全域 integration writer一次收斂。
4. 全域 writer scan、dependency scan、full tests 只在兩份計劃都完成 focused gates 後執行一次。

## 8. Agent 執行紀律與 handoff 格式

每個 Agent／lane 開始前必須回報：

```text
Package ID:
Base branch / HEAD:
Scope:
Owner:
Write set:
Shared hot spots:
Dependencies:
Acceptance commands:
Forbidden effects:
```

每次 handoff 只回報：

```text
Completed:
Changed paths:
Tests: passed | failed | blocked | not_run
DB gates: PASS | BLOCKED | NOT_RUN（如適用）
Live drift found:
Remaining blocker:
Next package:
```

禁止事項：

- 不自行 commit、push、開 PR、切 branch、reset、clean 或 stash。
- 不以舊 test expectation 反推新規格；舊 history tests 應由新 contract test 取代，不是把 assertion 改綠。
- 不將 anomaly history 搬到另一張「archive」table 或 JSON blob 偽裝成瘦身。
- 不把已退役 source 改名成 `legacy`、`compat`、`v1`、`deprecated` 後繼續留在 production tree。
- 不保留「目前無 caller、也無 current owner，但可能以後用到」的程式或測試。
- 不刪 owner Domain 的正式 business events／receipts。
- 不在 owner predicate readback 失敗時刪除 current issue。
- 不用 UI filter 隱藏仍在 DB 的 legacy active row冒充 migration 完成。
- 不把 automation capability 缺失變成 direct SQL 或跨 Domain shortcut。

## 9. 完成定義

只有以下全部成立，本計劃才可標 `completed`：

1. current SSOT 已反映 latest human decision。
2. 43 碼完成 15／25／3 的實際 runtime cutover，不只是文件分類。
3. 異常的唯一持久狀態是目前仍 active 的 current issue row；predicate 消失即刪除。
4. claim／resolve、occurrence、tracking、reclassification、historical umbrella 全部停止寫入且完成入口／schema 退役。
5. owner work items、輸入驗證與人工 actions 都有 typed replacement，沒有功能斷線。
6. 自動化只包含能力已存在且結果唯一、安全、可重播的流程；其餘保持 blocked 或未實作。
7. fresh clone、preserve-data upgrade、API、React、Browser、writer／entry scan 與 full suites 都有 final PASS evidence。
8. 未執行 production／`union_db`／provider／deployment 或未授權 destructive target。
9. dependency disposition inventory 無 `pending`、`unknown` 或無 owner 列；所有應刪 production source、test、
   fixture、route、client、worker wiring 與 runtime table reference 均已實際移除。

## 10. Blocked table／source／test disposition inventory

本節是 base `eaca24903197400343e72342e5f03970e0fda078` 的 path-coverage inventory，不是
正式執行裁決。現有 `delete | rewrite | keep-owner` 只是 candidate disposition；第 10.5 節要求的
exact successor、caller、readback、gate、focused tests 與 final oracle 任一缺漏，該列即固定
`SPEC_GAP`。不得因此處已列 path 就執行刪檔、rewrite 或 compatibility retirement。

### 10.1 25 張 runtime table：全部 delete

| Table | Disposition | Replacement／處置 |
|---|---|---|
| `anomaly_current_alerts` | `delete` | 由 fresh owner recheck 重建到 `current_anomaly_issues`；不得 copy inactive／resolved row |
| `anomaly_workflow_events` | `delete` | 無 replacement；owner Preview／Apply receipt 提供正式操作證據 |
| `finance_anomaly_occurrences` | `delete` | Finance Import／Client Finance／Staff Payables／Government Subsidy owner facts |
| `anomaly_consumer_checkpoints` | `delete` | general durable-job idempotency＋owner-version bounded recheck |
| `anomaly_root_fact_projection_receipts` | `delete` | current reconcile transaction result，不保存 anomaly projection history |
| `anomaly_root_fact_snapshots` | `delete` | `current_anomaly_issues` 的 current typed details |
| `import_warning_occurrences` | `delete` | Case Import／Orders／Finance Import owner review row |
| `import_warning_tracking_events` | `delete` | 無 replacement；移除 tracking machine |
| `import_warning_current_tasks` | `delete` | owner work queue Query |
| `import_warning_resubmission_associations` | `delete` | owner resubmission command／receipt；不保存 anomaly association copy |
| `import_warning_tracking_receipts` | `delete` | owner command receipt |
| `import_warning_tracking_outbox` | `delete` | owner outbox，只在 owner action 真需要後續處理時建立 |
| `anomaly_reclassification_dispositions` | `delete` | 無 replacement；owner work item／current registry直接切換 |
| `anomaly_reclassification_receipts` | `delete` | 無 replacement |
| `anomaly_reclassification_batch_receipts` | `delete` | DB migration final receipt只證明cutover，不保存逐alert處分 |
| `historical_baseline_occurrences` | `delete` | Orders historical owner roots／各 Domain work item |
| `historical_baseline_projector_receipts` | `delete` | 無 replacement |
| `historical_baseline_umbrella_memberships` | `delete` | 各 owner Query直接表達缺根項目 |
| `historical_baseline_successors` | `delete` | 無 umbrella successor；owner root自己完成 |
| `historical_baseline_v2_occurrence_state_events` | `delete` | Orders historical owner facts；不保存 anomaly state event |
| `historical_baseline_v2_projector_receipts` | `delete` | 無 replacement |
| `historical_baseline_v2_active_membership_snapshots` | `delete` | bounded owner work-item Query |
| `historical_baseline_v2_projector_deliveries` | `delete` | 無 anomaly delivery；必要 owner job 使用 general durable job |
| `historical_baseline_v2_source_checkpoints` | `delete` | owner-version bounded query cursor |
| `historical_baseline_v2_post_commit_readbacks` | `delete` | owner command receipt／fresh Query readback |

上述 table 的舊 schema-part 檔案 `113`、`127`、`195`、`1009`、`1011`、`1014` 裁決為
`keep-owner(Global Migration provenance)`：已發布 release hash 不可改寫，但它們不得留在 final runtime
schema，也不得再被 application source／current tests引用。successor destructive release 必須 drop objects；
fresh canonical assembly 的最終 exact schema 必須不存在這 25 張表。

### 10.2 Production source disposition

#### Delete：整個 path 退役

| Path | Replacement／刪除 gate |
|---|---|
| `api/dependencies/anomaly_necessity_migration.py` | necessity migration routes移除後刪除 |
| `api/dependencies/import_warning_tracking.py` | owner review/work-queue dependencies接通後刪除 |
| `api/routes/anomaly_necessity_migration.py` | 無 replacement；current registry直接採新裁決 |
| `api/routes/import_warning_tracking.py` | Case Import／Orders／Finance owner routes |
| `api/schemas/anomaly_necessity_migration.py` | 無 replacement |
| `api/schemas/import_warning_tracking.py` | owner-specific typed schemas |
| `domains/anomalies/import_warning_tracking.py` | owner review models |
| `domains/anomalies/maintenance.py` | bounded recheck改由新 `current_issue_recheck.py`；不搬 reclassification/dead-letter machine |
| `domains/anomalies/root_fact_projection.py` | 新 `current_issue.py`；不搬 Finance occurrence model |
| `subsystems/anomalies/alert_workflow.py` | 新 `current_issue_application.py`；不搬 claim／resolve |
| `subsystems/anomalies/beclass_import_anomaly_consumer.py` | Case Import current detector／owner review Query |
| `subsystems/anomalies/beclass_import_outbox_consumer.py` | 同上；不再建立 warning occurrence |
| `subsystems/anomalies/client_over_refund_recovery_anomaly_consumer.py` | Client Finance recovery work queue |
| `subsystems/anomalies/client_refund_underpayment_anomaly_consumer.py` | Client Finance remaining-refund Query |
| `subsystems/anomalies/government_overpayment_anomaly_consumer.py` | Government Subsidy disposition work queue |
| `subsystems/anomalies/hcm_import_review_outbox_consumer.py` | Case Import owner review＋IMPORT-003 bounded recheck |
| `subsystems/anomalies/hcm_resubmission_outbox_consumer.py` | HCM owner Apply後直接排 bounded recheck |
| `subsystems/anomalies/historical_baseline_projection.py` | 各 owner work-item Query；umbrella全面退役 |
| `subsystems/anomalies/historical_order_adoption_outbox_consumer.py` | Orders adoption review Query直接讀 owner root |
| `subsystems/anomalies/historical_order_review_remediation_outbox_consumer.py` | Orders remediation Apply後fresh owner Query |
| `subsystems/anomalies/import_warning_projection_retry.py` | general durable-job retry；無 warning projector retry machine |
| `subsystems/anomalies/import_warning_tracking_workflow.py` | owner-specific review workflows |
| `subsystems/anomalies/maintenance_workflow.py` | 新 bounded current recheck application；不搬 reclassification |
| `subsystems/anomalies/necessity_migration_policy.py` | 無 replacement |
| `subsystems/anomalies/process_reminder_anomaly_source.py` | 拆至 Orders／Scheduling／LINE／Finance owner Query與15-code detectors |
| `subsystems/anomalies/staff_overpayment_recovery_anomaly_consumer.py` | Staff Payables recovery work queue |
| `subsystems/anomalies/staff_payout_difference_anomaly_consumer.py` | Staff Payables remaining／recovery Query |
| `subsystems/anomalies/system_alert_projection.py` | 新唯一 current issue storage；舊 `system_alerts` projection不得並存 |
| `infrastructure/mysql/anomaly_maintenance_repository.py` | 新 current issue bounded recheck repository；不搬 history tables |
| `infrastructure/mysql/anomaly_reclassification_owner_query_adapter.py` | owner work queue直接讀 owning repository |
| `infrastructure/mysql/anomaly_root_fact_projection_repository.py` | 新 `current_issue_repository.py` |
| `infrastructure/mysql/beclass_import_review_anomaly_source.py` | 新 Case Import current detector／owner review adapter |
| `infrastructure/mysql/historical_baseline_projector_checkpoint.py` | owner version/cursor |
| `infrastructure/mysql/historical_baseline_projector_delivery.py` | 無 anomaly delivery replacement |
| `infrastructure/mysql/historical_baseline_projector_read_model.py` | 各 owner typed Query |
| `infrastructure/mysql/historical_baseline_projector_repository.py` | 各 owner repository |
| `infrastructure/mysql/historical_baseline_projector_worker.py` | 無 umbrella worker |
| `infrastructure/mysql/import_warning_auto_resolution.py` | owner action後recheck；無 tracking auto-resolve |
| `infrastructure/mysql/import_warning_tracking_repository.py` | owner review repositories |
| `infrastructure/mysql/line_notification_anomaly_worker.py` | LINE delivery post-commit current recheck job |
| `infrastructure/mysql/process_reminder_anomaly_source.py` | bounded owner adapters，按 Domain拆檔 |

#### Rewrite：保留 current 行為，舊 symbol 必須消失

| Path | Target responsibility |
|---|---|
| `api/main.py` | 移除 necessity/import-warning routers；mount current issue routes |
| `api/dependencies/anomaly_recovery.py` | 只組合 current detail/action/recheck dependencies |
| `api/dependencies/anomaly_registry.py` | 組合15-code registry＋current repository |
| `api/routes/anomaly_recovery.py` | current owner action context；移除 occurrence、timeline、anomaly dead-letter surface |
| `api/routes/anomaly_registry.py` | current-only list/detail；移除 claim／resolve |
| `api/schemas/anomaly_recovery.py` | closed current details/action union；移除 occurrence/timeline/dead-letter models |
| `api/schemas/anomaly_registry.py` | current-only summary/detail；移除 workflow status/receipt bodies |
| `domains/anomalies/__init__.py` | 只export current issue contracts |
| `domains/anomalies/recovery_context.py` | current owner evidence＋manual action；無 history timeline |
| `domains/anomalies/registry.py` | 精確15-code registry；無 lifecycle/audit/work-item/occurrence kind |
| `domains/case_import/beclass_warning_review.py` | BeClass owner review item；不產生 anomaly occurrence |
| `domains/case_import/hcm_import_review.py` | HCM owner review＋IMPORT-003 candidate；不展開 warning occurrence |
| `domains/finance_import/warning_review.py` | Finance owner review item；不建立 anomaly occurrence |
| `domains/orders/historical_order_warning_review.py` | Orders owner review item；不建立 warning occurrence |
| `subsystems/anomalies/case_anomaly_readback.py` | current issue＋owner blocker readback |
| `subsystems/anomalies/finance_import_anomaly_consumer.py` | 只保留 `IMPORT-006` current recheck；manual review移至owner queue |
| `subsystems/anomalies/finance_import_review_alert.py` | 只產生 `IMPORT-006` typed candidate |
| `subsystems/anomalies/government_return_outbound_overage_anomaly_source.py` | `GOVSUB-007` current candidate |
| `subsystems/anomalies/government_subsidy_anomaly_source.py` | `GOVSUB-001/002` current candidates |
| `subsystems/anomalies/government_subsidy_assignment_drift_anomaly_source.py` | `GOVSUB-005` current candidate |
| `subsystems/anomalies/government_subsidy_integrity_anomaly_source.py` | `GOVSUB-003` current candidate |
| `subsystems/anomalies/government_subsidy_reversal_anomaly_source.py` | `GOVSUB-004` current candidate |
| `subsystems/anomalies/line_notification_alert.py` | terminal-only `LINE-006` candidate |
| `subsystems/anomalies/line_notification_anomaly_projector.py` | rename/rewrite為LINE bounded current recheck；不用 anomaly checkpoint |
| `subsystems/anomalies/outbox_worker.py` | dispatch owner-triggered bounded rechecks；不投遞 retired consumers |
| `subsystems/anomalies/root_fact_projection_workflow.py` | rename/rewrite為scope reconciler；upsert present＋delete absent |
| `subsystems/anomalies/scheduling_coverage_anomaly_consumer.py` | `SCHEDULE-006` current candidate/recheck |
| `subsystems/anomalies/service_before_replacement_projection.py` | `SCHEDULE-002` current predicate；不產生 occurrence/successor history |
| `subsystems/anomalies/source_version.py` | owner-version scope helper；移除 legacy daily anomaly version fallback |
| `subsystems/anomalies/staff_payables_anomaly_source.py` | 只保留 `PAYOUT-002` current detector；其他改owner queue |
| `infrastructure/mysql/anomaly_registry_repository.py` | current table Query／scope reconcile；無 workflow/occurrence writes |
| `infrastructure/mysql/case_anomaly_readback_adapter.py` | current issue／owner facts typed readback |
| `infrastructure/mysql/finance_import_repository.py` | 保留Finance owner交易；移除 anomaly resolve/occurrence writes，改post-commit recheck intent |
| `infrastructure/mysql/government_return_outbound_overage_anomaly_source.py` | `GOVSUB-007` bounded owner adapter |
| `infrastructure/mysql/government_subsidy_anomaly_source.py` | `GOVSUB-001/002` bounded owner adapter |
| `infrastructure/mysql/government_subsidy_assignment_drift_anomaly_source.py` | `GOVSUB-005` bounded owner adapter |
| `infrastructure/mysql/government_subsidy_integrity_anomaly_source.py` | `GOVSUB-003` bounded owner adapter |
| `infrastructure/mysql/government_subsidy_reversal_anomaly_source.py` | `GOVSUB-004` bounded owner adapter |
| `infrastructure/mysql/hcm_resubmission_repository.py` | 保留Case Import owner修正；移除 warning table FK/association，改owner receipt＋recheck |
| `infrastructure/mysql/historical_order_review_remediation_repository.py` | 保留Orders remediation；不join anomaly current row、不寫anomaly disposition |
| `infrastructure/mysql/scheduling_coverage_anomaly_source.py` | `SCHEDULE-006` bounded owner adapter |
| `infrastructure/mysql/staff_payout_repository.py` | 保留Staff Payables owner交易；移除 anomaly difference/history writes，改owner queue＋recheck |
| `scripts/migrate_preserved_database_additive_schema.py` | 納入successor destructive release、descriptor、plan、resume/rollback |
| `scripts/plan_legacy_ui_dataset_integration.py` | 將舊anomaly tables列為drop/not-preserved；新current table由fresh recheck重建 |
| `scripts/rebuild_legacy_ui_dataset_projections.py` | 只重建新current issue projection；移除舊table名稱 |
| `scripts/seed_validation_beclass_review.py` | seed Case Import owner review／current pairing issue |
| `scripts/seed_validation_finance_manual_review.py` | seed Finance owner manual-review row，不seed finance occurrence |
| `scripts/verify_finance_manual_review_scenario.py` | 驗 owner queue＋posting readback，不查workflow status |
| `subsystems/validation_dataset/inspection.py` | 驗 current row存在/消失與owner queue；移除workflow event檢查 |

#### Keep-owner：不得被 anomaly cleanup 刪除

| Path／artifact | Owner 與保留理由 |
|---|---|
| `domains/orders/historical_operational_baseline.py` | Orders；正式歷史案件 owner-root completeness，不是 anomaly history；移除任何 umbrella adapter依賴後保留 |
| `infrastructure/mysql/historical_baseline_staff_payables_owner_adapter.py` | Staff Payables owner facts供Orders completeness Query；不寫25張退役table |
| `db/schema_parts/113_anomaly_registry_projection.sql` | Global Migration immutable predecessor provenance only |
| `db/schema_parts/127_anomaly_root_fact_projector.sql` | Global Migration immutable predecessor provenance only |
| `db/schema_parts/165_anomaly_workflow_event_idempotency_widen.sql` | Global Migration predecessor provenance；current code零引用 |
| `db/schema_parts/195_import_warning_tracking.sql` | Global Migration immutable predecessor provenance only |
| `db/schema_parts/1009_anomaly_reclassification_disposition.sql` | Global Migration immutable predecessor provenance only |
| `db/schema_parts/1011_historical_baseline_projector.sql` | Global Migration immutable predecessor provenance only |
| `db/schema_parts/1014_historical_baseline_projector_v2.sql` | Global Migration immutable predecessor provenance only |

### 10.3 React production source disposition

| Path | Disposition | Replacement／target |
|---|---|---|
| `ui_react/src/adapters/import_warning/import_warning_transition_adapter.ts` | `delete` | owner review adapters |
| `ui_react/src/api/import_warning/import_warning_transition_client.ts` | `delete` | Case Import／Orders／Finance owner clients |
| `ui_react/src/api/import_warning/import_warning_transition_errors.ts` | `delete` | owner typed errors |
| `ui_react/src/api/import_warning/import_warning_transition_schemas.ts` | `delete` | owner schemas |
| `ui_react/src/api/anomalies/historical_baseline_projector_client.ts` | `delete` | owner work-item clients |
| `ui_react/src/api/anomalies/historical_baseline_projector_schemas.ts` | `delete` | owner typed schemas |
| `ui_react/src/adapters/anomalies/anomaly_detail_adapter.ts` | `rewrite` | current detail，不映射timeline/workflow |
| `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts` | `rewrite` | current-only summary/count |
| `ui_react/src/adapters/anomalies/client_settlement_target.ts` | `rewrite` | Client Finance owner work-item/action target |
| `ui_react/src/adapters/anomalies/finance_owner_recovery_target.ts` | `rewrite` | owner action dispatcher，不讀occurrence snapshot |
| `ui_react/src/api/anomalies/anomaly_detail_client.ts` | `rewrite` | current typed detail/action |
| `ui_react/src/api/anomalies/anomaly_detail_errors.ts` | `rewrite` | current query/action errors |
| `ui_react/src/api/anomalies/anomaly_detail_schemas.ts` | `rewrite` | 15-code closed details union |
| `ui_react/src/api/anomalies/anomaly_query_client.ts` | `rewrite` | 只有 current-only list/detail；owner work queues 使用各自 Domain client |
| `ui_react/src/api/anomalies/anomaly_query_errors.ts` | `rewrite` | current query errors |
| `ui_react/src/api/anomalies/anomaly_query_schemas.ts` | `rewrite` | 移除workflow/import-warning task models |
| `ui_react/src/pages/AnomaliesPage.tsx` | `rewrite` | current issues＋owner actions；無claim/resolved/history UI |

### 10.4 Direct-dependency tests／fixtures disposition

#### Delete：只保護退役語意

| Path | Replacement |
|---|---|
| `tests/test_anomaly_necessity_migration_disposable_mysql_e2e.py` | current cutover migration E2E |
| `tests/test_anomaly_reclassification_domain.py` | 無；reclassification退役 |
| `tests/test_anomaly_reclassification_owner_query_adapter.py` | owner work-queue Query tests |
| `tests/test_anomaly_reclassification_repository.py` | 無；repository退役 |
| `tests/test_anomaly_reclassification_schema_contract.py` | successor drop-schema contract |
| `tests/test_anomaly_reclassification_workflow.py` | 無；workflow退役 |
| `tests/test_beclass_warning_occurrences.py` | Case Import owner review/current pairing tests |
| `tests/test_finance_import_warning_occurrences.py` | Finance owner review tests |
| `tests/test_hcm_import_warning_occurrences.py` | Case Import owner review tests |
| `tests/test_historical_baseline_projector_schema_contract.py` | successor drop-schema/fresh absence test |
| `tests/test_historical_baseline_projector_v2_schema_contract.py` | successor drop-schema/fresh absence test |
| `tests/test_historical_order_warning_occurrences.py` | Orders review work-item test |
| `tests/test_import_warning_auto_resolution_guard.py` | owner completion＋current row deletion tests |
| `tests/test_import_warning_projection_retry.py` | general durable-job retry tests（若仍需要） |
| `tests/test_import_warning_tracking.py` | owner review tests |
| `tests/test_import_warning_tracking_api.py` | owner API tests |
| `tests/test_import_warning_tracking_api_client.py` | owner client tests |
| `tests/test_import_warning_tracking_api_disposable_mysql_e2e.py` | owner review E2E |
| `tests/test_import_warning_tracking_disposable_mysql_e2e.py` | owner review E2E |
| `tests/test_import_warning_tracking_workflow.py` | owner workflow tests |
| `tests/test_import_warning_transition_receipt_contract.py` | owner receipt tests |
| `ui_react/src/tests/anomalies_warning_transition_flow.test.tsx` | owner review/action flow tests |
| `ui_react/src/tests/fixtures/anomalies/historical_baseline_projector_contract_fixtures.ts` | owner work-item fixtures |
| `ui_react/src/tests/fixtures/import_warning/import_warning_transition_contract_fixtures.ts` | owner review fixtures |
| `ui_react/src/tests/import_warning_transition_adapter.test.ts` | owner adapter tests |
| `ui_react/src/tests/import_warning_transition_client.test.ts` | owner client tests |

#### Rewrite／rename：保留業務情境，舊 assertion 與舊 path 必須消失

| Current path | Target test responsibility |
|---|---|
| `tests/test_anomaly_closed_loop_disposable_mysql_e2e.py` | rename為current issue manual action→owner readback→row delete E2E |
| `tests/test_anomaly_finance_import_writer_boundary.py` | current repository唯一writer＋Finance owner boundary |
| `tests/test_anomaly_root_fact_projection_repository.py` | rename為current issue scope reconcile repository tests |
| `tests/test_client_beclass_binding_disposable_mysql_e2e.py` | owner binding＋IMPORT-003/BECLASS current row deletion；不查occurrence |
| `tests/test_client_refund_return_anomaly_snapshot.py` | Client Finance refund-return owner work-item view |
| `tests/test_finance_import_disposable_mysql_e2e.py` | split：Finance owner import E2E＋`IMPORT-006` current recheck；刪tracking assertions |
| `tests/test_finance_recovery_anomaly_disposable_mysql_e2e.py` | owner recovery/action E2E；只對15-code issue驗current deletion |
| `tests/test_historical_operational_baseline_schema_contract.py` | 保留Orders 1010 owner schema；更新release chain不把1011/1014當current dependency |
| `tests/test_historical_order_adoption_noop_constraint_schema.py` | 保留Orders 1008 constraint；更新successor chain引用 |
| `tests/test_migrate_legacy_ui_dataset.py` | old anomaly tables not-preserved＋new current rebuild |
| `tests/test_plan_legacy_ui_dataset_integration.py` | 同上 |
| `tests/test_refund_return_review_disposable_mysql_e2e.py` | owner review work item出現/消失；不查CLIENTREFUND anomaly status |
| `tests/test_wp77_disposable_mysql_e2e.py` | Staff/HCM/BeClass owner adoption/review；刪warning tracking assertions |
| `tests/integration/test_historical_order_workbook.py` | Orders adoption/review work item；刪warning occurrence/alert history assertions |
| `ui_react/src/tests/anomalies_detail_referral_flow.test.tsx` | current detail＋owner manual action flow |
| `ui_react/src/tests/anomalies_entry_cutover.test.tsx` | current-only entry與removed legacy surfaces |
| `ui_react/src/tests/anomalies_finance_correction_flow.test.tsx` | Finance owner work-item/action＋fresh current recheck |
| `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx` | 保留no-direct-mutation；移除tracking語意 |
| `ui_react/src/tests/anomalies_page_real_data.test.tsx` | current-only real API states |
| `ui_react/src/tests/anomaly_detail_adapter.test.ts` | current typed details；無timeline |
| `ui_react/src/tests/anomaly_detail_client.test.ts` | current detail/action client |
| `ui_react/src/tests/anomaly_query_adapter.test.ts` | current-only counts/mapping |
| `ui_react/src/tests/anomaly_query_client.test.ts` | current-only list/detail＋schema failure |
| `ui_react/src/tests/challenger_2_anomaly_adapter_kpi_stress.test.ts` | current severity/category counts；刪claimed/resolved KPI |
| `ui_react/src/tests/challenger_phase2d_anomalies.test.tsx` | current page interaction／accessibility |
| `ui_react/src/tests/fixtures/anomalies/anomaly_detail_contract_fixtures.ts` | 15-code current detail fixtures |
| `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts` | current-only query fixtures |

#### Keep-owner：內容不得再依賴25張退役table

| Path | Owner／限制 |
|---|---|
| `tests/test_historical_baseline_staff_payables_owner_adapter.py` | Staff Payables owner-root completeness；保持純 owner readback |
| `tests/test_historical_operational_baseline_catalog_v2.py` | Orders owner completeness catalog；不是 anomaly occurrence catalog |

### 10.5 Inventory execution-readiness gate

上述清單覆蓋 base scan 的 99 個直接 table-family reference path，以及未直接寫 table
名稱但組成舊 Anomalies core 的 Domain／Subsystem／API／Infrastructure／React modules。
`99/99` 只證明 path coverage，不證明 disposition 可執行。每列必須補齊並通過：

1. exact current symbols／objects 與 inbound callers；
2. canonical owner 與 current owner-spec reference；
3. `delete | rewrite | keep-owner` candidate 的 exact successor path／symbol，或明確 `none`；
4. replacement Query／UI／readback 可達證據；
5. deletion／rewrite gate 與 focused tests；
6. final writer／reference／entry scan oracle。

未補齊前狀態固定 `blocked_inventory_contract`。後續施工期每次 package 結束才重新執行：

1. 25 個 table name 的 production-source reference scan；
2. `claim | resolve | occurrence | import_warning_tracking | anomaly_reclassification | historical_baseline_projector`
   symbol／route／React surface scan；
3. deleted path inbound-reference scan；
4. new current table writer scan。

新增命中若不在本節，integration writer必須先判定它是 base drift 或本次新增錯誤；未補裁決前 package
固定 `blocked_inventory_drift`。Final gate 要求所有 `delete` path實際不存在、所有 `rewrite` 舊 symbol不存在、
所有 `keep-owner` path對25張退役table為零引用。
