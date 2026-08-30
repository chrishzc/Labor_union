---
doc_type: execution-plan
task_id: CUR-LINE-BACKEND-SLIMMING-01
declared_status: blocked
owner: LINE / Integration
depends_on: Task 97 repository-local final artifacts (satisfied; refresh input only)
blocks: Task 96 LINE M1-M4 closure replanning
conflict_priority: Task 97 wins over this task on every overlapping path or decision
authority_date: 2026-08-29
execution_authority: approved_for_inventory_and_non_destructive_refactor
current_blocker: awaiting_user_resume_and_current_head_refresh
---

# LINE 後端瘦身執行計劃

> Current status由`LINE_BACKEND_SLIMMING_POST_PREP_AMENDMENT.md`擁有：Task 97 repository-local prerequisite
> 已完成，但本計畫維持`blocked / awaiting-user-resume-and-current-head-refresh`；不得據此自動啟動S2～S9。

> Current execution order：Task 97 final artifacts（已存在）→ 使用者恢復＋current-head refresh → 本任務 → LINE regression →
> freeze slimmed LINE backend baseline → 重新評估 Task 96 coverage／wiring／Authority → M1～M4 closure。
> 本任務不得順手補 Task 96 功能缺口。
> 若執行期間與 Task 97 的 path、Authority、交易邊界、governance artifact 或驗證結論衝突，
> 固定以 Task 97 為優先；受影響 slimming 結論與 patch 先標 stale，待 Task 97 current evidence 後重新推導。

## 0. 任務目的

本計劃只處理 **LINE 後端瘦身與架構收斂**。

本階段不得新增 M1～M4 功能，不得為了補齊 E2E 建新 framework，不得重做既有 domain 能力。

最終目標：

> LINE 只保留「系統旁路」與「LINE 自身產品能力」兩類責任。
> 任何 Client / Staff / Scheduling / Matching / Assignment / Customer Service / Payroll / Payables 等正式業務狀態，必須由原 domain owner 保存與推進。
> LINE 不建立平行業務狀態機。

---

# 1. 目標架構

## 1.1 LINE 只分成兩部分

### A. LINE as Side-channel

LINE 作為系統旁路，負責：

- 接收既有 domain 產生的通知需求
- 暫存待發送訊息
- 暫存等待 LINE 使用者回答的 interaction
- 當原 domain 狀態推進時發送提醒
- 接收 LINE 回覆 / postback
- 將使用者 intent 送回原本負責的 application/API/domain
- 保存必要的 delivery/provider 技術結果

LINE 不負責：

- Client 正式狀態
- Staff 正式狀態
- Scheduling 正式狀態
- Matching 正式狀態
- Assignment 正式狀態
- Customer Service 正式狀態
- Payroll 正式狀態
- Payables 正式狀態

正確方向：

```text
Domain state change
→ notification / interaction intent
→ LINE side-channel
→ LINE sends message
→ user responds
→ LINE maps response to intent
→ existing Application/API boundary
→ original Domain
→ Repository
→ DB
```

禁止：

```text
LINE webhook/postback
→ other-domain Repository
→ DB
```

---

### B. LINE as Product

LINE 自身產品能力可保留：

- LINE identity binding
- LINE webhook
- LINE postback
- LIFF entry / LINE-specific integration
- Flex presentation
- Rich Menu
- LINE provider delivery
- provider receipt / retry / idempotency
- LINE-owned configuration
- AI assistant / knowledge interaction（僅限目前正式允許範圍）

這些能力可以有自己的 LINE-owned state，但不得因此取得其他 domain 的 mutation ownership。

---

# 2. 核心判斷規則

對 LINE backend 中每一個 persisted state / model / status / workflow 問：

> **如果完全拿掉 LINE，這個狀態還需不需要存在？**

## 2.1 `keep-owner`

如果答案是「沒有 LINE 就沒有意義」，可由 LINE 擁有。

例：

- LINE identity binding
- LINE webhook event idempotency
- LINE provider delivery result
- Rich Menu draft / revision / publication state
- provider resource id
- LINE-specific AI conversation/session

---

## 2.2 `keep-adapter`

保留必要的技術邊界，但必須保持薄。

例：

- webhook route adapter
- postback adapter
- LINE provider adapter
- LINE persistence adapter
- LIFF auth/identity adapter

Adapter 不得承載 business lifecycle。

---

## 2.3 `rewrite`

責任仍然需要，但目前：

- 放錯 layer
- 跨 domain ownership
- 重複既有正式 API/application contract
- 建立平行 workflow
- provider 直接知道 business semantics
- 多條正式 mutation/send path 並存

則標記 `rewrite`。

---

## 2.4 `delete`

符合以下情況：

- current runtime 已無 responsibility
- 無 production caller
- 無 route / worker / job / config registration
- 非 canonical LINE intrinsic responsibility
- 功能已被正式 architecture / decision 淘汰
- 只是重複另一條正式 owner path
- 只剩 obsolete test 依賴

則標記 `delete`。

`merge` 不作為獨立分類；需要合併時視為 `rewrite` 的實作手段。

---

# 3. 硬性 Architecture Guardrails

以下規則全程不可違反。

## 3.1 不跨 Application/API Boundary 直接碰 DB

正確：

```text
LINE / LIFF / Webhook / Postback
→ existing API/Application boundary
→ Domain owner
→ Repository
→ DB
```

禁止：

```text
LINE
→ ClientRepository
→ DB
```

禁止：

```text
LINE
→ StaffRepository
→ DB
```

禁止：

```text
LINE
→ MatchingRepository
→ DB
```

禁止：

```text
LINE
→ Payroll / Payables table
```

---

## 3.2 LINE 不複製正式業務狀態

禁止在 LINE 內建立或保留平行 business lifecycle，例如：

```text
profile_pending
profile_approved
profile_applied

leave_confirmed
extension_approved
substitution_required

matching_pending
recipient_accepted
recipient_rejected

payroll_pending
payable_generated
```

若這些狀態在沒有 LINE 的情況下仍需存在，應回到原 domain owner。

---

## 3.3 Workflow state 不等於 ownership

LINE 可以知道：

```text
interaction_id
source_domain
source_object_id
expected_action
expires_at
waiting / answered / expired / cancelled
```

但不因此擁有 `source_object` 的正式 business lifecycle。

---

## 3.4 優先 wiring，不重造 API

如果 existing formal API/application service 已能完成 mutation：

```text
LINE
→ existing formal API/application service
→ domain
→ repository
→ DB
```

不得新增：

- LINE-specific duplicate mutation API
- temporary direct-DB API
- test-only production shortcut
- ad-hoc SQL mutation path

---


# 3.5 Agent 執行裁決：哪些事項不得再詢問

以下事項視為本計劃已正式裁決。執行 Agent 不得因為保守、偏好不同或想重做設計而重新向使用者確認：

1. LINE 僅有兩類正式責任：
   - Side-channel
   - LINE Product
2. LINE 不擁有 Client / Staff / Scheduling / Matching / Assignment / Customer Service / Payroll / Payables 等正式業務狀態。
3. LINE 不建立 M1～M4 平行 business state machine。
4. `PendingInteraction` 只能保存最小 transient context，不得演變成正式 business lifecycle。
5. Existing formal API/application service 優先於新增 LINE-specific mutation path。
6. 禁止跨 API/application/domain boundary 直接 mutation DB。
7. 無 current caller 的 dead production code，不因 obsolete tests 而保留。
8. Full/rejected AI 不得因「未來可能需要」而保留 speculative framework。
9. 本輪只做瘦身、ownership 收斂、dead-path cleanup 與 regression；不新增 M1～M4 功能。
10. Workflow state 不等於 domain ownership。
11. DB state 正確不足以證明架構正確；mutation path 必須經正式 owner boundary。
12. 不得為了減少修改量建立 temporary direct-write shortcut。
13. 若 existing formal owner path 已存在，必須 reuse，不得建立 duplicate LINE-specific API/service。
14. `merge` 不是獨立決策；需要合併時屬於 `rewrite` 的實作方法。

Agent 應先依 repo、正式規格、caller、route、worker、config、migration 與 runtime evidence 自行完成判斷。

不得把「可以從 code/spec 唯一推得的答案」升級成使用者問題。

---

# 3.6 唯一允許阻擋實作的三類問題

Agent 可以直接開始 S0 / S1。

只有遇到以下三類情況，才允許停止該子項並提出 blocking question。

## A. `UNKNOWN_OWNER`

適用條件：

```text
同一 persisted state / mutation responsibility
無法從正式規格、domain boundary、current caller 或 existing application contract
唯一判定真正 owner。
```

例如：

```text
某 review/request state
可能屬於 LINE
也可能屬於 Client
也可能屬於共用 Review owner
且 current spec 無法裁決
```

處理：

```text
STOP only this sub-item
→ mark UNKNOWN_OWNER
→ 提供候選 owner + evidence + architecture consequence
→ 等待 Authority 決策
```

不得：

- 自己挑最方便的 owner
- 暫時塞回 LINE
- 用 direct DB bypass 繼續

---

## B. `UNKNOWN_CANONICAL_PATH`

適用條件：

```text
真正 domain owner 已明確，
但 repo 中存在兩個以上可 mutation 同一 business object 的 API/application service，
且無法從正式規格/current registration/current caller 唯一判定 canonical entry。
```

例如：

```text
LINE postback 需要更新 Client profile
但存在 ClientServiceA / ClientApplicationB / legacy HTTP API
且 current evidence 無法證明哪條是正式 path
```

處理：

```text
STOP only this rewrite
→ mark UNKNOWN_CANONICAL_PATH
→ 列候選 path
→ 列 current caller / validation / transaction / ownership evidence
→ 等待裁決
```

不得自行新建第四條 path。

---

## C. `DESTRUCTIVE_RETENTION_DECISION`

適用條件：

- drop table
- drop column
- destructive migration
- 刪除可能仍需 audit/legal/reconciliation 的歷史資料
- 移除 public/external HTTP contract，而 external caller 尚未證明不存在
- 清除 provider receipt / identity history / review history 等 retention 要求不明資料

預設安全策略：

```text
先停止新寫入
→ 移除 runtime dependency
→ 移除 duplicate owner/write path
→ 保留 schema/history
→ 將 destructive cleanup 標記為 DESTRUCTIVE_RETENTION_DECISION
```

除非 current canonical spec 已明確允許 destructive cleanup，否則本輪不得直接 drop。

---

# 3.7 不得阻擋的常見情況

以下情況不得中止整個瘦身任務：

### Dead code caller 已可證明

直接依 Delete Gate 處理。

### 只有 obsolete tests 引用

刪除/重寫 obsolete tests，不得保留 dead production architecture。

### Identity module 檔名相近

先查 invariant/caller/layer；不得只因是否 merge 而詢問。

### Rich Menu draft 是否保留

先依 current behavior 判斷是否有：

- cross-session persistence
- revision
- publication lock
- provider lifecycle

只有 evidence 真正不足才升級為 `UNKNOWN_OWNER` 或 retention 問題。

### AI extension point

若 current runtime 無 caller 且 full AI 為正式 REJECT：

直接列 `delete candidate` 並完成 caller/config/runtime gate。

不得詢問是否「為未來先留」。

---

# 3.8 Blocking Question 格式

若真的遇到三類 blocker，Agent 不得只丟一句「請確認」。

必須使用：

```text
Blocker:
UNKNOWN_OWNER | UNKNOWN_CANONICAL_PATH | DESTRUCTIVE_RETENTION_DECISION

Affected:
<file / state / route / table / service>

Current evidence:
- ...
- ...

Why code/spec cannot decide:
...

Options:
A. ...
   consequence: ...
B. ...
   consequence: ...

Recommended:
<若 evidence 足以偏向其中一項，可給 recommendation；否則明確寫 no recommendation>

Can continue elsewhere:
YES
```

Blocking question 只阻擋受影響子項。

其他已可判斷的 S0～S9 工作必須繼續。

# 4. 瘦身期間禁止事項

本任務不得：

- 新增 M1～M4 功能
- 補 profile 新 feature
- 補 safe-link feature
- 補 recipient business rule
- 新增完整 AI phase
- 推翻既有 Authority 決策
- 新增 generic BaseService / BaseRepository framework
- 為統一而製造新的 abstraction hierarchy
- 將多個小 module 合成 god service
- 使用 direct DB shortcut
- 使用 fixture / manual DB edit 假裝 runtime closure
- 為 obsolete tests 保留 dead production code
- 把 transient interaction 設計成永久 event history，除非正式需求明確要求

---

# 5. 執行方法

每個階段都必須遵循：

```text
Inventory
→ classify
→ identify canonical owner
→ identify existing formal path
→ rewrite/delete
→ focused tests
→ regression
```

不得先重構再找用途。

---

# S0 — LINE State / Persistence Inventory

## Goal

完整盤點 LINE backend 現在到底保存哪些 state。

## Agent Tasks

搜尋 LINE backend 相關：

- DB tables
- ORM models
- repositories
- persisted dataclasses/entities
- status enums
- workflow enums
- draft/review/request models
- queue/outbox models
- webhook event persistence
- provider receipt persistence
- rich menu persistence
- identity persistence
- AI/session persistence
- media/storage persistence

同時搜尋所有 LINE code 對其他 domain 的：

- repository import
- ORM model import
- SQL
- session.add
- session.delete
- session.execute
- direct update
- direct cross-domain service access

## Output

建立工作表：

```text
LINE_BACKEND_STATE_AUDIT.md
```

只需以下欄位：

| item | current_owner/path | real_owner | class | action | reason |
|---|---|---|---|---|---|

`class` 僅允許：

- intrinsic
- transient
- duplicated-business
- adapter
- dead/legacy

`action` 僅允許：

- keep-owner
- keep-adapter
- rewrite
- delete

## Acceptance

- 所有 LINE persisted state 均已列入
- 所有跨 domain write dependency 均已列入
- 不修改 production behavior

---

# S1 — Ownership Classification

## Goal

把 LINE state 分成三類：

1. LINE intrinsic state
2. LINE transient interaction state
3. duplicated business state

## Agent Tasks

對每一項使用：

> 如果完全拿掉 LINE，這個狀態還需要存在嗎？

### LINE intrinsic

優先 `keep-owner`：

- identity binding
- webhook idempotency
- delivery/provider state
- Rich Menu provider/publication state
- LINE-owned AI/session state

### LINE transient

僅保留最小必要 interaction metadata。

優先結構：

```text
interaction_id
source_domain
source_object_id
intent_type / expected_action
expires_at
status
```

不得把 business result 複製進 interaction model。

### duplicated business

全部標記：

```text
rewrite
```

或若完全 obsolete：

```text
delete
```

## Acceptance

不存在「owner 不明但繼續實作」的項目。

Owner 不明時：

```text
STOP only affected sub-item
→ mark UNKNOWN_OWNER
→ continue all other decidable slimming work
```

本瘦身任務不得自行創造新的 business owner，也不得因單一 blocker 停止整體 S0/S1。

---

# S2 — Remove Cross-Domain Ownership

## Goal

移除 LINE 對其他 domain 正式狀態的 ownership。

## Priority Domains

至少檢查：

- Client
- Staff
- Scheduling
- Matching
- Assignment
- Customer Service
- Payroll
- Payables

## Agent Tasks

搜尋所有：

```text
LINE code
→ other-domain repository/model/table
```

逐一判斷 existing formal API/application service。

### Existing formal path exists

改為：

```text
LINE
→ existing Application/API
→ Domain
→ Repository
→ DB
```

Action:

```text
rewrite
```

### No formal path, but owner clear

本瘦身任務：

- 不建立 direct DB shortcut
- 不擴張 scope 補完整 feature
- 記錄 architecture gap
- 保留目前安全可行的最小行為
- 必要時 STOP 該子項

### Dead duplicate path

Action:

```text
delete
```

## Acceptance

- LINE production code 不直接 mutate 其他 domain repository/table
- 所有 mutation 走正式 boundary
- 瘦身前既有功能 regression 不退步

---

# S3 — Converge Side-channel Model

## Goal

LINE 系統旁路收斂到最少必要概念。

原則上只保留：

1. Notification Intent
2. Pending Interaction

不得為 M1 / M2 / M3 / M4 各建立獨立 LINE business workflow。

---

## S3.1 Notification Intent

代表：

> 某 domain 需要透過 LINE 通知某人。

可包含必要欄位：

```text
source_domain
source_object_id
recipient / recipient_ref
message_type
payload/reference
delivery_status
provider_receipt/reference
retry metadata
```

不要保存其他 domain 的完整 snapshot，除非 delivery immutable payload 必須如此。

---

## S3.2 Pending Interaction

代表：

> LINE 正等待使用者針對某一 business object 回答。

可包含：

```text
interaction_id
source_domain
source_object_id
expected_action
expires_at
status
```

狀態最多：

```text
waiting
answered
expired
cancelled
```

如果目前模型有：

```text
approved
matched
substituted
leave_finalized
profile_applied
payable_created
```

應移回 domain owner 或刪除。

## Acceptance

LINE side-channel 不再包含 M1～M4 各自的 business state machine。

---

# S4 — Delivery / Outbox / Provider Convergence

## Goal

所有正式 LINE outbound message 最後只走一條 delivery pipeline。

目標：

```text
Notification / Interaction Intent
→ LINE Delivery
→ Outbox
→ Worker
→ LINE Provider Adapter
→ Provider Response
→ Receipt
```

## Agent Tasks

搜尋所有：

- provider SDK direct call
- direct push
- direct reply
- special M1 sender
- special M2 sender
- special M3 sender
- special M4 sender
- admin direct sender
- background job direct LINE API
- legacy delivery service

### Current caller exists

改接唯一正式 pipeline：

```text
rewrite
```

### No caller

```text
delete
```

## Provider Boundary

Provider adapter 只應知道：

```text
recipient
payload
provider config
provider response
```

不得知道：

- Client lifecycle
- Staff leave
- matching decision
- substitute logic
- payroll consequence
- CS escalation business rule

## Acceptance

- 一種 production outbound intent 只有一條正式 provider path
- 不存在 route/service/job 各自直連 LINE provider 的平行路徑
- retry/idempotency/receipt responsibility 集中

---

# S5 — Identity Slimming

## Goal

保留真正 LINE-owned identity invariant，移除 business workflow 膨脹。

LINE Identity 僅應擁有：

```text
LINE user
↔
system actor
```

合理 invariant：

- bind
- unbind
- replacement
- verification
- conflict
- revocation

## Agent Tasks

特別檢查目前相鄰 identity modules，例如：

```text
identities.py
identity_binding.py
identity_flow.py
```

不要因檔名接近直接 merge。

逐檔判斷：

### 真正 identity invariant

```text
keep-owner
```

### thin technical adapter

```text
keep-adapter
```

### Client/Staff/business flow orchestration

移到適當 application/orchestration layer：

```text
rewrite
```

### duplicate CRUD wrapper / obsolete flow

```text
delete
```

## Acceptance

LINE identity module 不保存：

- Client lifecycle
- Staff employment lifecycle
- Case lifecycle
- registration lifecycle

除非只是呼叫正式 owner boundary 的 orchestration，不得直接持久化其狀態。

---

# S6 — Rich Menu Slimming

## Goal

Rich Menu 保留為 LINE 自身產品能力，但只保留一套 lifecycle。

合理 LINE-owned state：

```text
draft
revision
validation state
publication status
provider resource id
published version
processing / provider failure state
```

## Target Path

```text
Draft
→ Validate
→ Publish Intent
→ Worker / Provider
→ Receipt
→ Published
```

## Agent Tasks

搜尋是否存在：

- parallel draft store
- legacy publish service
- direct provider publication
- test shortcut used in production
- multiple publication lifecycle
- duplicate provider resource state

分類：

- canonical lifecycle → keep-owner
- thin provider boundary → keep-adapter
- current duplicate path → rewrite
- dead path → delete

## Acceptance

Rich Menu 最終只有一個正式 publish lifecycle。

---

# S7 — AI / Legacy / Rejected Path Cleanup

## Goal

刪除 current architecture 不使用的 speculative 或 rejected LINE backend code。

目前原則：

- deterministic routing / current allowed knowledge flow 保留
- full autonomous AI phase 若仍為正式 REJECT，不得因原 Eraser 想像而復活

## Agent Tasks

搜尋：

- AI router
- model/provider abstraction
- confidence routing
- autonomous action branch
- obsolete prompts
- obsolete feedback pipeline
- unused model config
- dead experimental endpoints
- legacy LINE services

每項必須查：

```text
production imports
callers
routes
config registration
worker registration
tests
```

只有 obsolete tests 引用，不構成保留理由。

## Acceptance

- current runtime 不再依賴的 AI/legacy production code 已清除
- current deterministic routing / knowledge / fallback 行為不退步

---

# S8 — Transient Lifecycle Cleanup

## Goal

LINE 暫存資料不演變成永久平行歷史庫。

## Agent Tasks

對：

- Pending Interaction
- Notification Intent
- review/request temporary objects
- provider temporary records
- staging objects

逐類定義最小 lifecycle：

```text
active
→ consumed / answered / rejected / expired / cancelled
→ cleanup / retention
```

禁止因方便 debug 就永久 mirror business state。

如果正式 domain 已保存 final truth：

LINE 不再永久保存完整：

- old state
- new state
- approved state
- applied state
- synced state

除非有明確 audit/legal/domain requirement。

## Acceptance

每一種 LINE transient state 都有：

- ownership
- terminal state
- cleanup/retention 行為

但不得新增複雜 event-sourcing/history framework。

---

# S9 — File / Test / Migration Cleanup + Regression

## Goal

完成檔案層級清理，刪除不再需要的 production/test/schema dependency，確認既有功能未退步。

## Agent Tasks

根據 S0～S8 最終分類：

### `keep-owner`

保留。

### `keep-adapter`

保留，但若含 business rule，繼續瘦薄。

### `rewrite`

完成移動/收斂後刪除原 duplicate path。

### `delete`

刪除：

- production code
- obsolete tests
- obsolete fixtures
- obsolete config
- obsolete registration

對 migrations / schema artifacts 採較嚴格規則：

- 若只是 dead runtime dependency：先停止寫入並移除 code dependency
- 若要 drop table / column 或刪 historical data：必須通過 `DESTRUCTIVE_RETENTION_DECISION`
- 若 current canonical spec 已明確允許，且 migration chain、安全回滾與 current runtime 均驗證完成，才可在本輪執行 destructive migration

不得留下：

```text
unused compatibility wrapper
deprecated alias
dead feature flag
duplicate model
duplicate repository
old service "just in case"
```

除非有 current external compatibility contract。

---

# 6. Delete Gate

任何檔案 / model / service / route 標為 `delete` 前，Agent 必須確認：

```text
1. no production import/caller
2. no route registration
3. no worker/job registration
4. no runtime/config/plugin registration
5. no current migration/runtime dependency
6. no canonical LINE intrinsic responsibility
7. no external compatibility contract
```

若 production path 已死，只有 obsolete tests 還引用：

```text
delete dead production path
+
delete/rewrite obsolete tests
```

不得為測試保留 dead architecture。

---

# 7. 每個修改單位的 Agent Checklist

每次準備改 code 前先回答：

```text
1. 這段 code 現在保存或推進什麼 state？
2. 如果沒有 LINE，這個 state 還需要存在嗎？
3. 真正 owner 是誰？
4. 是否已有正式 API/application service？
5. LINE 需要的是 owner、adapter，還是 transient interaction？
6. 是否存在另一條重複 write/send path？
7. 此修改應標 keep-owner / keep-adapter / rewrite / delete 哪一類？
8. 修改後用什麼既有 regression 證明功能未退步？
```

若第 3 題無法回答：

```text
STOP only affected sub-item
→ UNKNOWN_OWNER
```

若第 4 題存在多個無法裁決的正式候選：

```text
STOP only affected rewrite
→ UNKNOWN_CANONICAL_PATH
```

若修改涉及 drop schema / historical retention / unknown external contract：

```text
STOP destructive step only
→ DESTRUCTIVE_RETENTION_DECISION
```

其他已可判斷工作必須繼續。不得用 direct DB shortcut 繼續。

---

# 8. 執行批次原則

每個 Agent work package 應小而可驗收。

建議每包只處理：

```text
one owner
or
one mutation path
or
one delivery path
or
one state family
```

不要一次「重構整個 LINE」。

每包格式：

```text
Task:
處理哪個 state/path。

Current:
目前 owner / caller / persistence / path。

Action:
keep-owner / keep-adapter / rewrite / delete。

Change:
最小必要修改。

Must Not:
本包禁止事項。

Verify:
focused test + relevant regression。

Done:
修改後只有一條 owner/path，且沒有 architecture bypass。
```

---

# 9. 建議執行順序

嚴格依序：

```text
S0 盤 LINE persistence / state
↓
S1 intrinsic / transient / duplicated-business 分類
↓
S2 清除跨 Domain ownership
↓
S3 收斂 Notification Intent + Pending Interaction
↓
S4 收斂 Delivery / Outbox / Provider
↓
S5 瘦 Identity
↓
S6 瘦 Rich Menu
↓
S7 清 rejected AI / legacy / dead paths
↓
S8 收斂 transient lifecycle / cleanup
↓
S9 刪 production/test/schema dead dependencies + regression
```

S0/S1 未完成前，不得大規模刪 code。

S2 是最高架構優先級。

---

# 10. Regression Scope

本計劃不要求補齊尚未完成的 M1～M4。

只要求瘦身前「已成立」的 LINE 行為在瘦身後不得退步。

至少針對目前已有能力檢查：

- LINE identity binding / unbind / replacement
- webhook/postback 基本處理
- existing LIFF entry integration
- current deterministic message routing
- current fallback / CS handoff
- current Rich Menu draft/publish behavior
- current delivery/outbox/worker/provider behavior
- existing Baby Log text flow
- existing M3 backend workflows
- existing current mobile/admin LINE-related surfaces where applicable

若某流程瘦身前就是 `not_run` / blocked：

不得在本任務中偽造 PASS。

---

# 11. 瘦身成功指標

不要以刪除 LOC 數量作為主要 KPI。

完成後比較：

```text
1. 同一 business mutation 的正式 write entry 數
2. LINE 對其他 domain repository/table 的直接 dependency 數
3. 代表同一 invariant 的 module/model 數
4. LINE provider 正式 send path 數
5. LINE 內重複保存其他 domain state 的位置數
6. current runtime 已不用但仍存在的 legacy path 數
7. LINE persisted business-status enum 數
```

目標：

- 1 → 越接近每 action 一條正式 path 越好
- 2 → 0
- 3 → 無無意義重複
- 4 → 1 個 canonical delivery pipeline
- 5 → 0
- 6 → 0
- 7 → 只剩 LINE intrinsic / transient status

---

# 12. Final Done Definition

只有同時符合以下條件，LINE 後端瘦身才算完成。

## Architecture

- LINE 只分成 Side-channel 與 LINE Product 兩類責任
- LINE 不擁有其他 domain 正式業務狀態
- LINE 不建立 M1～M4 平行狀態機
- LINE 不直接 mutation 其他 domain repository/table
- 所有跨 domain mutation 走正式 API/Application → Domain → Repository → DB

## Side-channel

- notification 有單一正式概念與 delivery path
- pending interaction 只保存最小 temporary context
- 回覆後 intent 交回原 domain
- business state 由原 domain 推進

## LINE Product

- Identity 只保存 LINE identity invariant
- Rich Menu 只有一套正式 lifecycle
- Webhook/Postback 保持薄
- Provider adapter 不承載 business semantics
- AI 不取得其他 domain mutation ownership

## Cleanup

- duplicate production paths 已收斂
- dead/legacy production code 已刪除
- obsolete tests/fixtures/config 一併清理
- 不保留「just in case」compatibility code
- 不新增 speculative framework

## Verification

- 所有受影響 focused tests 通過
- 相關 existing regression 通過
- 原本 blocked/not_run 的能力仍誠實標示 blocked/not_run
- 無靠 direct DB、fixture、manual mutation 偽造結果

---

# 13. 本任務結束後才允許的下一步

本瘦身完成並通過 regression 後，才重新進行：

```text
M1～M4 Coverage
→ Wiring
→ genuine Authority Closure
→ Vertical E2E
```

後續規劃必須以瘦身後的實際架構與正式 owner 為唯一基線，不得沿用已刪除的 LINE workflow/state 假設。
