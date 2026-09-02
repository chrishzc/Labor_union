# LINE 四大模組詳細測試手冊與 Agent 前置條件規範

> **文件版本**：v2.0（2026-09-02）  
> **對齊程式版本**：`main @ 0988f6c430472343662aa1f8989ab2af9732bde3`  
> **適用範圍**：LINE 官方帳號、LIFF、FastAPI、MySQL、React 管理後台、M1～M4 repository-local 與手機 E2E 驗收。  
> **權威依據**：`document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`  
> **目的**：讓 Agent 先完成可自動化的測試前置資料與 readback，測試者拿手機後只執行真正需要 LINE／LIFF／Rich Menu 的最後操作。

---

## 0. 驗收原則：前置資料與被測流程必須分開

本手冊把每個案例拆成兩段：

1. **Agent 前置任務**：建立或整理 development/test 測試資料、檢查服務、建立測試案件狀態、準備候選人、產生 readback。
2. **手機驗收**：由真人在 LINE／LIFF 實際操作，驗證畫面、身分、postback、推播與 Rich Menu。

### 0.1 不得把 fixture 當成流程通過

- 若 current owner 已有正式 `Query / Preview / Apply / receipt / readback`，Agent 必須優先走正式 owner contract。
- 若目前**沒有正式建立訂單 API**，Agent 可以在 `development/test` DB 建立最小測試訂單 fixture，但必須標記為 `PRECONDITION_FIXTURE`。
- `PRECONDITION_FIXTURE` 只證明「測試起點已準備」，**不證明訂單建立流程本身通過**。
- 不得直接 INSERT/UPDATE `matching_coordination_events`、outbox、delivery task、customer-service escalation 等被測結果表來製造成功結果。
- 不得在 production DB 建 fixture。
- 真 LINE provider、真 Rich Menu 發布、真群組推播等外部副作用，除非測試者明確要求執行，Agent 前置階段只準備到 provider boundary 前。

### 0.2 驗收層級

每個案例結束時需標記：

| 層級 | 定義 |
|---|---|
| `PREPARED` | Agent 已完成前置資料與 readback，尚未拿手機操作 |
| `REPO_LOCAL_PASS` | owner contract、commit/outbox/readback/fallback 已由測試證明 |
| `MOBILE_PASS` | 真人已在 LINE／LIFF 手機端完成直接操作 |
| `PROVIDER_PASS` | 真 LINE/Gemini provider 已取得成功結果 |
| `NOT_RUN` | 尚未執行該層級 |
| `BLOCKED` | 有明確 blocker，必須記錄 blocker code／原因 |

只看到 API、table、UI 或 unit test 存在，不得直接標 `MOBILE_PASS`。

---

# 1. 最低設備與帳號需求

## 1.1 不需要三支手機

目前建議：

- **最低：1 個個人 LINE 帳號**
  - 可依序測 M0、M1 客戶身分、解除綁定、再綁月嫂／管理角色、M2 AI、部分 M4。
- **建議：2 個個人 LINE 帳號**
  - 帳號 A：產婦／客戶。
  - 帳號 B：月嫂。
  - 可完整驗證 M3「雙方同時收到不同 recipient 訊息」。
- **不強制第 3 個個人 LINE 帳號**。
  - 工會管理角色可在測試完其他角色後，用同一帳號解除綁定再測。
- **LINE 測試群組**：M4 群組告警需要一個可加入官方帳號的測試群組，但不等於需要第三支手機。

## 1.2 重複使用同一帳號的方法

管理後台已有正式解除綁定流程：

```text
LINE 管理 → LINE 身分綁定與授權管理
→ 選擇目前帳號
→ 檢查解除影響
→ 填寫解除原因
→ 勾選確認
→ 提交解除
```

後端 contract：

```text
POST /api/v1/line/identity-bindings/{line_user_id}/revocation/preview
POST /api/v1/line/identity-bindings/{line_user_id}/revocation/apply
```

解除不是直接 DELETE binding，而是 durable revocation + Rich Menu 回復流程。若 reset 失敗，另有 retry；system admin 只有在允許條件下可 manual-complete。

因此可以：

```text
帳號 A 綁客戶 → 測試 → 解除
→ 帳號 A 綁月嫂 → 測試 → 解除
→ 帳號 A 綁管理角色 → 測試
```

---

# 2. Agent 共用前置任務

測試者可以先交給 Agent 執行以下任務，完成後再拿手機。

## 2.1 Agent 安全檢查

Agent 必須先確認：

```text
APP_ENV != production
```

以及：

```text
GET http://127.0.0.1:8000/health
```

應回 `200`。

目前常用環境設定：

```text
DB_HOST
DB_PORT
DB_USER
DB_PASSWORD
DB_DATABASE
LINE_LIFF_ID
LINE_PUBLIC_BASE_URL 或 BASE_URL
```

MySQL development 預設通常為 `127.0.0.1:3306 / union_db`，但 Agent 應讀目前環境，不得假設固定密碼。

React：

- development Vite：`http://localhost:5173/admin/`
- build artifact：FastAPI `/admin`

## 2.2 Agent 建立測試資料的優先順序

Agent 必須依序選擇：

1. current owner 的正式 `Preview → Apply → Readback`。
2. repo 既有 development/test fixture writer 或 bootstrap。
3. 只有前兩者不存在時，才可建立 **development-only SQL fixture**。

如果使用第 3 種，必須：

- 先讀 current schema，不可沿用手冊舊 SQL。
- 只建立測試所需的最小 root facts。
- 使用 transaction。
- 不直接製造被測流程的 event/outbox/receipt 成功結果。
- 使用明確測試識別，例如 actor/reason/source 中含 `lu_test_` 或 `LINE-E2E-<run-id>`。
- 建完立即 readback。
- 回報 cleanup 方式。

## 2.3 「建立訂單」的 current 限制

目前 `api/routes/orders.py` 沒有 canonical `POST /orders` 建單 API。

`/api/v1/cases/{case_no}/architecture-bootstrap/*` 是針對**既有案件**補齊 Finance / Payroll / Scheduling 架構，不是建立訂單。

因此 Agent 若為 M3/M4 準備一筆測試訂單：

1. 優先找 current import/bootstrap/test fixture writer。
2. 若沒有符合本案例的 writer，可在 development DB 建 `PRECONDITION_FIXTURE` 訂單及必要 client/staff root facts。
3. 訂單存在後，再使用：

```text
GET  /api/v1/cases/{case_no}/architecture-bootstrap/status
POST /api/v1/cases/{case_no}/architecture-bootstrap/preview
POST /api/v1/cases/{case_no}/architecture-bootstrap/apply
```

補齊案件架構。

**禁止**為了讓 M3 看起來成功而直接寫 `matching_coordination_*` 結果表；M3 必須由正式 Matching Preview/Apply 產生。

## 2.4 Agent 完成前置後必須回傳「手機測試包」

格式固定：

```text
TEST RUN ID:
目前環境: development / test
FastAPI health: PASS/FAIL
Admin UI: URL
Public LINE URL:
LIFF runtime: READY/BLOCKED
Gemini: READY/BLOCKED/NOT_REQUIRED

測試案例:
case_no:
client_id / client_name:
staff_id / staff_name:
第二 staff（若需要）:
目前 matching/scheduling 狀態:
目前 LINE binding 狀態:
需要使用的手機帳號: A / B

Agent 已完成:
- ...

你現在只要用手機做:
1. ...
2. ...
3. ...

預期結果:
- ...

測完 cleanup:
- ...
```

如果 Agent 無法建立某個 root fact，必須回 `BLOCKED`，不得假造資料。

---

# 3. 模組零：新好友 Onboarding（前導，不列入四大模組核心分數）

## M0-01 新好友加入

### Agent 前置

- 確認 webhook runtime 啟用。
- 確認 public HTTPS URL 可由 LINE 連線。
- 確認 default Rich Menu publication/readback 存在；若未發布，回 `BLOCKED: default_menu_not_published`。
- 不需要建立訂單。

### 手機操作

1. 封鎖後解除封鎖，或用尚未加入的測試帳號加入官方帳號。
2. 檢查歡迎訊息。
3. 檢查 default Rich Menu。

### 驗收

- Follow webhook 有 ingress evidence。
- 歡迎訊息 delivery 有 durable task/readback。
- Rich Menu 顯示 default menu。

---

# 4. 模組一：LIFF、登記、身分與角色切換

## M1-01 Gateway LIFF 導流

### Agent 前置

- 確認 `LINE_LIFF_ID` 已配置。
- 確認 `GET /api/v1/line/identity/runtime-config` 可正常回應。
- 確認 public base URL 是 HTTPS（localhost 開發例外僅限本機）。
- 確認手機測試帳號目前沒有不需要的舊 binding；有的話先走正式 revocation。

### 手機操作

1. 點 Rich Menu【服務登記】。
2. 開啟 `gateway.html`。
3. 測「未申請市府平台」：應導向新竹市政府平台。
4. 回來後測「已申請市府平台」：應進 `/line-registration?flow_id=...`。

### Current 技術路徑

```text
POST /api/v1/line/identity/flow/open
POST /api/v1/line/identity/flow/validate
```

LIFF 使用 `liff.getIDToken()`；不得由前端任意指定真實 LINE User ID。

---

## M1-02 需求調查表 Preview → Apply

### Agent 前置

- 不先替手機帳號寫 binding。
- 確認 registration page 可讀 current LIFF config。
- 準備一組不會與正式資料衝突的測試姓名、電話、地址。

### 手機操作

1. 從 M1-01 進入 `/line-registration`。
2. 填必填欄位與需求調查。
3. 故意輸入錯誤手機格式，確認 UI 阻擋。
4. 填正確資料。
5. 第一次送出只產生 preview。
6. 確認去識別摘要後再 Apply。

### Current API

```text
POST /api/v1/line/identity/registration/preview
POST /api/v1/line/identity/registration/apply
```

### 驗收

- Preview 不寫正式登記。
- Apply 後可 readback `provisional_client_registrations` 對應紀錄。
- Current implementation 可在 apply 流程建立 `clients` 與 `beclass_records` 並關聯回 registration；因此**不可再用「clients 必須完全不新增」作為舊版驗收條件**。
- LINE confirmation 必須經 durable delivery task。

---

## M1-03 客戶身分綁定

### Agent 前置

Agent 準備一個 current `clients` 中可供測試的客戶 root fact；若本案例需要既有案件，再準備 `case_no`。

不得直接建立最終 LINE binding。

### 手機操作

透過 current 客戶身分驗證入口完成：

```text
POST /api/v1/line/identity/customer/preview
POST /api/v1/line/identity/customer/apply
```

### 驗收

- preview 命中正確客戶。
- apply 後 binding readback 為 current bound 狀態。
- Rich Menu 切至對應角色選單時必須有 publication/delivery evidence。

---

## M1-04 月嫂身分綁定

### Agent 前置

- 準備一筆 `staff` 測試月嫂，狀態需符合 current staff owner 規則。
- 回報姓名、測試身分資料與 staff_id；不要把真個資寫進手冊。
- 若帳號 A 前一案例已綁客戶且要重用，先完成 revocation。

### 手機操作

Current API：

```text
POST /api/v1/line/identity/staff/preview
POST /api/v1/line/identity/staff/apply
```

### 驗收

- 正確月嫂可綁定。
- 錯誤資料不得建立有效 binding。
- 成功後 role context 與 Rich Menu 對應 staff。

---

## M1-05 管理角色綁定

### Agent 前置

- 建立／確認一個 development 管理員帳號，具本案例所需 capability。
- **不得在手冊、Git、聊天回覆中寫真密碼。**
- 使用者自行在安全環境取得測試密碼。

### 手機操作

使用 current admin identity flow：

```text
POST /api/v1/line/identity/admin/preview
POST /api/v1/line/identity/admin/apply
```

### 驗收

- 管理角色只能綁定符合權限的帳號。
- 群組環境不得暴露管理密碼或 credential。

---

## M1-06 解除綁定並重複使用同一支手機

### Agent 前置

- 確認 default Rich Menu publication 存在。
- 找出手機帳號 current binding readback。

### 管理後台操作

1. LINE 身分綁定與授權管理。
2. 選擇該 LINE User。
3. 「檢查解除影響」。
4. 填原因、確認。
5. 「提交解除」。

### API

```text
POST /api/v1/line/identity-bindings/{line_user_id}/revocation/preview
POST /api/v1/line/identity-bindings/{line_user_id}/revocation/apply
```

### 驗收

- 不直接 DELETE binding。
- revocation saga 有 request/readback。
- Rich Menu reset 成功後 binding 完成撤銷。
- 若 reset 失敗，應可 retry；manual-complete 只能依 system-admin 規則使用。

此案例是「只有一支手機」時的核心 reset 步驟。

---

## M1-07 雙角色隔離

### Agent 前置

- 同一 LINE User 準備 customer + staff 兩種 current binding（使用正式 owner flow；不可偽造 selected role）。
- 為兩個角色各準備至少一筆可 readback 資料。

### 手機操作

1. 切 customer role，讀客戶功能。
2. 切 staff role，讀月嫂功能。

### 驗收

- customer 不得讀 staff 私有資料。
- staff 不得讀其他客戶資料。
- role change 要有 current role-context/readback。

---

# 5. 模組二：AI 客服、QA、Gemini 與安全 fallback

> Current M2 已不是舊版「手動新增 INITIAL_RULES 後直接發布」的模型。正式 QA 來源為 `document/line/AI客服QA題庫.jsonl`；只有 `status=ready` 可自動回答。

## M2-00 Agent 前置總檢查

Agent 應先執行：

1. `GET /api/v1/system/llm/api-key/status`
2. 若未設定，請測試者自行在 UI 輸入 Google AI Studio key；Agent 不得要求讀回 Key。
3. `POST /api/v1/system/llm/connection-test`
4. `GET /api/v1/line/ai-events/qa-catalog`
5. 確認 Knowledge READY index 可用。
6. 在 AI 客服工作室執行一次 `/semantic-test` smoke test。

Agent 回報只包含 `configured/connected/model/status`，不得輸出 secret。

---

## M2-01 確定性 Tier 1

### 手機操作

輸入 current deterministic alias，例如功能總覽／客服等已配置固定指令。

### 驗收

- 命中 deterministic route 時不需要 Gemini 自由回答。
- 輸出必須由 server-owned router 決定。
- 不因未知文字執行外部 action。

---

## M2-02 正式 QA + Gemini 語意選擇

### Agent 前置

Agent 從 `/qa-catalog` 選 3 筆 `ready` QA，回傳：

```text
QA ID
canonical question
1 個 alias
```

不要事先修改答案。

### 手機操作

用自然口語改寫提問，例如不要逐字照 canonical question。

### Current M2 路徑

```text
LINE question
→ Knowledge READY index
→ Chroma 以 category/tag/question/aliases 找候選
→ Gemini 僅選 candidate QA ID 或 UNSUPPORTED
→ server 取 curated QA 的正式 answer
→ LINE answer
```

### 驗收

- Gemini 不得自由撰寫政策答案。
- 最終 answer 必須來自 selected QA 的 approved `answer`。
- citation/readback 可追溯來源。

---

## M2-03 非 ready QA 不得自動回答

### Agent 前置

從 QA catalog 各選一筆可用的：

```text
missing
partial
review_required
manual_only
```

若某狀態目前沒有資料，標 `NOT_APPLICABLE`。

### 手機／真實 M2 測試

提出對應問題。

### 驗收

- 不可把非 ready 項目當核准答案。
- 無可信候選應走 unsupported／安全 fallback。
- 不得由 Gemini 補寫政策內容。

---

## M2-04 模糊問題與 unsupported

### 測試文字

```text
時間問題
asdfghjk
今天天氣真好
```

### 驗收

分清兩種機制：

1. **deterministic router preview** 可有 confidence bands 與 clarify/safe menu。
2. **Gemini + Knowledge semantic QA** 不把 Gemini 當成百分比信心來源；候選不足、非法 ID、UNSUPPORTED、index unavailable、Gemini unavailable 都必須 fail closed。

---

## M2-05 明確轉真人

### 手機操作

```text
幫我轉真人
這不是我要問的，找客服
```

### 驗收

- 自動回答停止或進入人工接管語意。
- 由 Customer Service owner 建立／取得 current ticket/escalation。
- 不得由 LLM 自行直接 INSERT ticket。

---

## M2-06 Feedback

### 手機操作

對回答點「未解決」。

### 驗收

- feedback durable readback 可見。
- unresolved 可形成正式 customer-service follow-up，而不是只有前端計數。

---

# 6. 模組三：Matching 雙向協調

## M3-00 Agent 一鍵建立手機測試案件

此階段是本手冊最重要的 Agent 前置。

### Agent 任務

請 Agent 建立一個全新的 development test run：

1. 建立／選擇測試 client。
2. 建立／選擇至少 2 位可測 staff。
3. 建立一筆 `PRECONDITION_FIXTURE` order（因 current 沒有 canonical create-order route）。
4. 確認 case_no 可由 current Orders readback 查到。
5. 呼叫 architecture bootstrap status；若需要，走 preview→apply 補齊架構。
6. 透過 current owner 準備 matching 所需 criteria/candidate availability/preferences。
7. **停在手機要參與的前一個狀態**，不可替手機點掉 customer/staff decision。
8. 回傳「手機測試包」。

### Agent 禁止事項

不得直接寫：

```text
matching_coordination_events
matching_coordination_apply_receipts
matching_coordination_outbox
line_delivery_tasks
```

來偽造 M3 pass。

---

## M3-01 Criteria snapshot / term diff

### Agent 前置

建立一個 initial criteria，例如：

```text
每日服務時段 07:30
需料理
指定區域
```

使用 current API：

```text
POST /api/v1/matching/coordination/criteria/preview
POST /api/v1/matching/coordination/criteria/apply
```

再準備一個 changed criteria；但先停在 diff preview 前或完成 initial state，依測試包說明。

### 驗收

使用：

```text
POST /api/v1/matching/coordination/criteria-diff/preview
POST /api/v1/matching/coordination/criteria-diff/apply
GET  /api/v1/matching/coordination/cases/{case_no}/readback
```

確認只重探受變更條件影響的候選，不把無關拒絕原因全部重送。

---

## M3-02 Caregiver willingness

### Agent 前置

讓案件處於「等待月嫂意願」；準備 staff B 對應 recipient/binding。

### 手機操作（帳號 B）

月嫂在 LINE 卡片選擇接受／拒絕。

### Current owner 驗收

```text
POST /api/v1/matching/coordination/caregiver-willingness/preview
POST /api/v1/matching/coordination/caregiver-willingness/apply
```

- decision 要有 event/receipt/readback。
- 不直接 UPDATE assignment 當作 willingness。

---

## M3-03 Zero Pool 協商

### Agent 前置

準備一筆 current matching package，確保合法計算結果為 zero pool；不得直接 INSERT zero-pool event。

### 手機操作（帳號 A）

收到替代條件 proposal，選擇：

- 接受調整。
- 保留原需求。

### Current API

```text
POST /api/v1/matching/coordination/zero-pool/preview
POST /api/v1/matching/coordination/zero-pool/apply
POST /api/v1/matching/coordination/customer-decision/preview
POST /api/v1/matching/coordination/customer-decision/apply
```

### 驗收

- proposal → customer decision 有完整 lineage。
- 不接受時不應偷偷改原訂單條件。
- 接受時後續變更必須交由正確 owner，不由 Matching 跨 owner 直寫。

---

## M3-04 Match Success 雙方 recipient

### 設備

本案例建議使用 **2 個不同 LINE User ID**。

### Agent 前置

- 帳號 A 對應 client。
- 帳號 B 對應 staff。
- Agent 準備到 conversion/assignment 前一狀態。

### 手機驗收

完成 final decision 後確認：

- A 收到 client 版本通知。
- B 收到 staff 版本通知。
- recipient 不可交換。

### Owner/API

```text
POST /api/v1/matching/coordination/conversion/preview
POST /api/v1/matching/coordination/conversion/apply
```

並 readback Matching outbox → LINE delivery task/result。

只有 repository local task 但未真的送到手機時，標 `REPO_LOCAL_PASS / MOBILE_NOT_RUN`，不可標完整通過。

---

# 7. 模組四：管理端、群組告警、客訴與代班財務

## M4-01 異常通知群組設定

### Agent 前置

- 確認測試管理員 capability。
- `GET /api/v1/admin/line/runtime-alert-targets/alert-group-context`
- 若已有舊測試群組，先用正式 reset preview/apply，而非直接清 DB。

### 手機操作

在測試 LINE 群組使用 current 群組設定指令／流程。

### Current owner

管理 API：

```text
GET  /api/v1/admin/line/runtime-alert-targets/alert-group-context
POST /api/v1/admin/line/runtime-alert-targets/group/preview
POST /api/v1/admin/line/runtime-alert-targets/group/apply
POST /api/v1/admin/line/runtime-alert-targets/group-reset/preview
POST /api/v1/admin/line/runtime-alert-targets/group-reset/apply
```

LINE ingress：

```text
POST /api/v1/line/system/alert-group
```

Current persistence owner 為 `line_alert_notification_targets` 等 runtime alert tables，不再以舊版 `system_settings.alert_group_id` 作為唯一驗收依據。

---

## M4-02 客訴 → Hold → HIGH escalation → Alert

### Agent 前置

- 確認 alert target 已 ready。
- 確認 Customer Service readback 可用。
- 不先建立假 HIGH escalation。

### 手機操作

帳號 A 輸入明確客訴，例如：

```text
我要退費，服務態度很差，請主管處理。
```

### 驗收

應由 canonical complaint ingress 形成：

```text
complaint
→ automation hold
→ customer_service_tickets / customer_service_escalations
→ masked alert intent
→ LINE delivery task
→ 管理端安全處理入口
```

- HIGH escalation 必須由 owner 產生，不可由 fixture 預先 INSERT。
- 群組內容需去識別化。

---

## M4-03 Mobile Admin / Safe Review Link

### Agent 前置

Agent 準備一筆**合法待審 root fact**，例如由正式 profile/rebind flow 建立 pending review；不得直接偽造「已核准」結果。

### 手機操作

1. 從 LINE 告警／選單打開 mobile admin 或 safe review link。
2. 查看去敏摘要/diff。
3. Preview approve/reject。
4. 人工確認後 Apply。

### 驗收

- token/actor/版本錯誤時 fail closed。
- Preview 不應直接寫正式資料。
- Apply 有 receipt/readback。

---

## M4-04 月嫂請假與代班

### Agent 一鍵前置

Agent：

1. 建一筆 development test order fixture。
2. 準備 client A、staff A、staff B。
3. 建 current assignment/scheduling root facts。
4. bootstrap 案件架構。
5. 確認 staff A 有可請假的 service day。
6. 停在「staff A 可從手機提出請假」的狀態。

### 手機操作

- staff A 提出請假。
- client A 接收順延／代班決策。
- 若拒絕順延，再由管理端安排 staff B。

### 驗收

Current leave root 包含 `staff_leave_requests`；後續 substitution 必須走 Scheduling/Leave owner，不以直接 UPDATE schedule 作為 pass。

---

## M4-05 代班後 Payroll / Staff Payables

### Agent 前置

可直接沿用 M4-04 已完成的測試案件；Agent 不得另造假的 payroll result。

Agent 執行 repository-local readback：

1. 檢查 assignment/service-day facts。
2. 觸發 current Payroll owner 所需的正式 rebuild/project path（若本環境已有對應 Apply）。
3. 讀取 `staff_obligation_events` / `staff_obligations` 等 current SSOT。
4. 回傳每位 staff 的 obligation lineage。

### 驗收

- 原月嫂與代班月嫂各自有正確 payable obligation。
- 金額來源可追到 assignment/service facts。
- 不再以舊版泛稱 `payroll_items` 是否有兩列作為唯一驗收。

---

# 8. Agent 快速前置 Prompt 範本

## 8.1 任一案例

```text
請替我準備 LINE 手機測試案例 <TEST-ID>。
限制：只能使用 development/test 環境，不觸發 production，不替我執行手機上的最終決策。
先讀 current main 的 owner/API/schema；能用 Preview/Apply 就不能直接 SQL。
若沒有正式建立訂單 API，可以建立 PRECONDITION_FIXTURE，但不得直接寫被測流程的 event/outbox/receipt/result。
完成後請只回傳「手機測試包」：case_no、client/staff 測試識別、目前狀態、你已做的前置、我手機接下來要點的 3~5 步、預期結果、cleanup。
```

## 8.2 M3 Zero Pool

```text
請替我準備 M3-03 Zero Pool 手機測試。
建立一筆 development-only 測試案件與必要 client/staff root facts，必要時做 architecture bootstrap。
使用 current Matching owner 建 initial criteria 與合法候選狀態，讓系統自然進入 zero-pool proposal；不要直接 INSERT matching_coordination_events/outbox。
停在產婦手機即將收到／處理 proposal 的前一步，回傳測試包。
```

## 8.3 M4 請假代班

```text
請替我準備 M4-04 請假代班手機測試。
建立 development test order、client A、staff A、staff B、assignment 與可請假的 service day，必要時完成 architecture bootstrap。
不得直接製造 leave/substitution/payroll 成功結果。
停在 staff A 可以從 LINE 送出請假申請的狀態，回傳 A/B 手機各自要操作什麼與後台 readback 點。
```

## 8.4 重用單一 LINE 帳號

```text
請替我把目前測試 LINE 帳號安全重置給下一個角色使用。
先讀 current binding，走 revocation preview/apply 與 Rich Menu reset；禁止直接 DELETE line identity binding。
完成後回傳 binding/current-fact readback 與是否已恢復 default menu。
```

---

# 9. 測試完成後 Cleanup

Agent 可協助 cleanup，但必須遵守 owner boundary。

1. LINE 身分：使用正式 revocation，不直接 DELETE。
2. Rich Menu / alert group：使用 current reset Preview/Apply。
3. Customer-service/matching/payroll 正式測試結果：保留 audit/receipt/event lineage，不刪 immutable evidence。
4. `PRECONDITION_FIXTURE`：只清理由 Agent 建立且能證明 ownership 的 development synthetic roots；不得誤刪正式資料。
5. 測完輸出：

```text
cleanup_status: COMPLETE / PARTIAL / BLOCKED
保留的 immutable evidence:
已撤銷的 LINE bindings:
已重設的 Rich Menu / alert target:
尚需人工處理:
```

---

# 10. 快速執行順序（手機時間最省）

若只有 1 支手機，建議：

```text
Agent 一次準備全部可共用資料
↓
M0
↓
M1 customer
↓
M2 AI QA / fallback / 真人客服
↓
M4 complaint / mobile admin
↓
解除 customer binding
↓
綁 staff
↓
M1 staff / M4 leave
↓
解除 staff binding
↓
需要時綁 admin role
```

若有第 2 支手機，再做：

```text
A = client
B = staff
→ M3 willingness
→ M3 zero pool/customer decision
→ M3 match success 雙 recipient
→ M4 leave/substitution 雙方閉環
```

這樣不需要為每個案例重新人工建立訂單或手動改資料庫；Agent 應先把案件準備到「手機下一步就能操作」的狀態。

---

# 11. Current main 關鍵對照表

| 能力 | Current route / owner |
|---|---|
| API health | `GET /health` |
| LIFF runtime | `GET /api/v1/line/identity/runtime-config` |
| Identity flow | `/api/v1/line/identity/flow/open`, `/flow/validate` |
| Customer binding | `/customer/preview`, `/customer/apply` |
| Staff binding | `/staff/preview`, `/staff/apply` |
| Admin binding | `/admin/preview`, `/admin/apply` |
| Registration | `/registration/preview`, `/registration/apply` |
| Binding revoke | `/api/v1/line/identity-bindings/{line_user_id}/revocation/*` |
| QA catalog | `GET /api/v1/line/ai-events/qa-catalog` |
| Real M2 test | `POST /api/v1/line/ai-events/semantic-test` |
| Gemini status/test | `/api/v1/system/llm/api-key/status`, `/connection-test` |
| Matching readback | `GET /api/v1/matching/coordination/cases/{case_no}/readback` |
| Matching operations | `/criteria/*`, `/criteria-diff/*`, `/caregiver-willingness/*`, `/zero-pool/*`, `/customer-decision/*`, `/conversion/*` |
| Case architecture bootstrap | `/api/v1/cases/{case_no}/architecture-bootstrap/*` |
| Alert target | `/api/v1/admin/line/runtime-alert-targets/*` |
| Customer Service | current `customer_service_tickets` + escalation owner |
| Leave root | `staff_leave_requests` |
| Payroll SSOT | `staff_obligations` / `staff_obligation_events` 等 current Payroll owner |

---

## 文件維護規則

- 此文件描述的是 **current main 可操作測試方法**，不是保存舊版 API 的歷史文件。
- main 若修改 route/schema/owner，應同步更新此手冊。
- Eraser 原始業務流程仍以正式基線保存；如果原圖與 current owner-safe implementation 不同，本手冊應寫 current 驗收方法，並標示 supersession，而不是要求測試者呼叫已不存在的 API。
- 禁止在此手冊寫任何 API Key、LINE Channel Secret、access token、管理員真密碼或 production credential。
