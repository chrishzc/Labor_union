# LINE 四大模組詳細測試手冊與 Agent 前置條件規範

> **文件版本**：v2.6（2026-09-14，M2 常見問答與 AI 智慧問答專屬 LIFF 重構、選單更新與零推播額度設計）
> **原始對齊程式版本**：`main @ 0988f6c430472343662aa1f8989ab2af9732bde3`；包含 PR #299 及後續對齊修訂。開始測試前須確認實際執行版本已包含修正，PR 存在不等於 main 已合併或環境已部署。
> **適用範圍**：LINE 官方帳號、LIFF、FastAPI、MySQL、React 管理後台、M1～M4 repository-local 與手機 E2E 驗收。
> **權威依據**：`document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`；同目錄規格 17、20 的 owner 邊界，以及 2026-09-13 使用者八點業務裁決（未解決客服工單回覆、月嫂履歷推薦卡兩大按鈕、Match_Success 群組通知、Zero-Pool 拒絕降維群組通知、確認實際服務時間、月嫂檔期試算通知專員）。現有實作與本手冊不得自行取消規格 26 的 required flow acceptance。
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

### 0.3 目前實測執行進度總表（持續更新）

| 項目代碼 | 測試情境與分支 | 驗收層級 | 驗收日期 | 實測說明與結果 |
|---|---|---|---|---|
| **M1-01 狀態 A** | 舊客完全命中 (陳雅婷 / `0912345678`) | `MOBILE_PASS` | 2026-09-07 | ✅ **實測通過**：`bind.html` 輸入後自動完成綁定，顯示案號【`CASE-2026-M301`】，無需重填問卷。 |
| **M1-01 狀態 B** | 有案號缺問卷 (李詩涵 / `0933111222`) | `MOBILE_PASS` | 2026-09-07 | ✅ **實測通過**：提示找到市府案號【`CASE-2026-STATE-B`】，自動預填姓名/手機/案號無縫跳轉 `register.html`，Email 必填檢核與一鍵送出均正常。 |
| **M1-01 狀態 C** | 名冊未同步/查無案號 (訪客臨時登記) | `MOBILE_PASS` | 2026-09-10 | ✅ 測試者確認手機實測通過。 |
| **M1-01 狀態 D** | 連續失敗協處 (2 次失敗自動開工單) | `MOBILE_PASS` | 2026-09-10 | ✅ 測試者確認手機實測通過。 |
| **M1-02** | 需求調查表一鍵送出與防呆檢核 | `MOBILE_PASS` | 2026-09-10 | ✅ 測試者確認手機實測通過。 |
| **M1-03** | 客戶身分綁定 | `MOBILE_PASS` | 2026-09-10 | ✅ 測試者確認手機實測通過。 |
| **M1-04** | 月嫂身分綁定（王美華 / staff `1`） | `MOBILE_PASS / PROVIDER_PASS` | 2026-09-10 | ✅ 手機完成正式綁定；canonical binding=`bound`、subject=`staff:1`，最新 Rich Menu binding outbox 已完成且無錯誤，LINE user menu readback 與新月嫂專屬選單一致。 |
| **M1-05** | 管理角色綁定 | `MOBILE_PASS` | 2026-09-10 | ✅ 測試者確認手機實測通過。 |
| **M1-06** | 管理後台正式解除 (Rich Menu 回復) | `MOBILE_PASS / PROVIDER_PASS` | 2026-09-10 | ✅ 首次回復因舊 provider menu ID 回覆 `404 richmenu not found` 而失敗；重新發布訪客選單（publication `#20`）後走正式 retry，binding=`revoked`、revocation=`completed`，LINE user Rich Menu readback 與新訪客選單一致。另重新發布客戶（`#21`）、月嫂（`#22`）、工會幹部（`#23`）選單，四套 provider existence readback 均為 HTTP 200，LINE 全域預設亦指向新訪客選單；測試者確認手機實測通過。 |
| **M2-01** | 圖文選單導流驗證（常見問答與 AI 智慧問答） | `REPO_LOCAL_PASS / PREPARED` | 2026-09-14 | ⏳ **待測**：訪客與客戶選單點擊【常見問答】與【AI 智慧問答】正確導向對應專屬 LIFF 分頁。 |
| **M2-02** | 常見問答 (FAQ) 分類與 AI 問答引導橫幅 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-14 | ⏳ **待測**：LIFF 常見問答可分類折疊閱讀，列表下方醒目卡片引導「沒看到想問的問題？試試看【AI 智慧問答】」，點擊一鍵切換。 |
| **M2-03** | AI 智慧問答 LIFF 檢索 (0 Push 額度) | `REPO_LOCAL_PASS / PREPARED` | 2026-09-14 | ⏳ **待測**：於 LIFF 內口語提問，即時呼叫後端 API 檢索工會核准解答，完全不消耗 LINE Push 額度。 |
| **M2-04** | AI 未支援問題與轉真人客服引導 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-14 | ⏳ **待測**：超出知識庫問題時，系統提示轉真人客服，引導用戶直接於 LINE 聊天室留言由專員親自服務。 |
| **M2-05** | LINE 聊天室真人專員回覆空間 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-14 | ⏳ **待測**：用戶直接於聊天室打字，確認 AI 助理不再搶答，工會專員可透過手機 LINE OA App 免費 1 對 1 回覆。 |
| **M2-06** | Feedback 閉環（未解決轉真人） | `MOBILE_PASS` | 2026-09-13 | ✅ **實測通過**：點擊「未解決」回覆已更新為「已收到您的回饋{ticket}。AI 問答系統已暫時關閉，您可以直接在此對話中留下訊息等待真人客服回應。」並開立客服追蹤工單。 |
| **M3-01** | Criteria snapshot / term diff | `REPO_LOCAL_PASS / USER_VERIFIED` | 2026-09-11 | ✅ 使用者已驗證；initial criteria、criteria diff、受影響 recipient 精確重送及 stale fail-closed 聚焦測試亦通過。 |
| **M3-02** | Caregiver willingness (月嫂意願) | `REPO_LOCAL_PASS / USER_VERIFIED` | 2026-09-11 | ✅ 使用者已驗證：月嫂已在 LINE 回覆願意；willingness event、receipt、lineage/readback 聚焦測試亦通過。 |
| **M3-02B** | 月嫂履歷推薦卡與客戶確認決策 | `MOBILE_PASS / PROVIDER_PASS` | 2026-09-14 | ✅ **實測通過**：工會端寄送月嫂推薦卡，客戶於 LINE 成功收到輪播卡，並完成點選確認（接受配對／專人協助決策分支均已驗收通過），後台狀態與即時回覆均驗證正常。 |
| **M3-03** | Zero Pool 協商與拒絕降維 | `REPO_LOCAL_PASS / MOBILE_PASS` | 2026-09-13 | ✅ **實測通過**：Zero Pool 自動詢問客戶替代條件；若客戶拒絕降維（回覆無法調整條件），系統自動向工會管理群組發送 `【媒合需要人工處理】` 告警卡，專員人工介入協調。 |
| **M3-04** | Match_Success 群組簽約通知 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：客戶接受配對後，向工會管理群組推播 `【案件媒合成功通知】`，由工會專員接手線上簽約。 |
| **M4-01** | 異常通知群組設定與 CAS 鎖定 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：支援管理員指令綁定單一異常群組、CAS 防併發及後台重設。 |
| **M4-02** | 客訴 → Hold → HIGH escalation → Alert | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：客訴建立 HIGH 工單、觸發案件進入 Hold 狀態並向群組推播告警。 |
| **M4-03** | Mobile Admin / Safe Review Link | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：群組告警卡附安全短效連結，一次性兌換與版本失效防護。 |
| **M4-04** | 月嫂請假與代班協調 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：月嫂提出請假待辦，工會受理並於案件行事曆完成代班排班。 |
| **M4-05** | 代班後 Payroll / Staff Payables | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：Scheduling 代班排定後自動投影 Payroll 責任分拆，薪資可追溯至排班事實。 |
| **M4-06** | 服務前時間確認與檔期試算 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：產婦確認實際服務時間（Actual Service Dates）；月嫂排班檔期由系統自動試算衝突並直接通知工會專員人工協調。 |

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

## 2.5 LINE 官方帳號 Push 額度節省策略與客服問答 LIFF 設計

LINE 官方帳號在生產環境中依「每月主動發送的 Push 訊息則數」計費（免費用量有限，超額需付費）。為避免 AI 客服與自動通知迅速吃光額度，本系統落實三大額度防禦支柱：

### 2.5.1 額度防禦支柱一：客服問答專屬 LIFF（Push 消耗降為 0）

- **計費痛點**：用戶若在 LINE 聊天室中與 AI 進行多輪對話，每次回答若超過 Webhook Reply Token 限制或採用非同步推播，每一句都會被計為 1 則付費 Push 費用。
- **解法**：
  1. 在各身分專屬 Rich Menu（訪客、客戶、月嫂）常設「常見問題／客服中心」按鈕，點擊開啟專屬 LIFF 頁面。
  2. 用戶在 LIFF 網頁中：
     - 瀏覽分類知識庫與常見問題（純 HTTP GET，0 LINE 訊息成本）。
     - 透過搜尋框輸入問題，直接呼叫後端 API 檢索確定性知識與語意答案（純 REST API 傳輸，0 額度成本）。
     - 若答案未解決，直接於 LIFF 內填寫諮詢表單送出（直接寫入 `customer_service_messages` 工單，0 額度成本）。
  3. **成效**：用戶的所有探索、問答、回饋與工單填寫都在 LIFF 內完成，**完全不消耗任何 LINE 官方帳號 Push 額度**。

### 2.5.2 額度防禦支柱二：聊天室即時 Webhook 嚴格遵守 Reply Token

- **規則**：用戶若直接在聊天室打字提問，後端 Webhook 處理時**僅允許使用該次請求提供的 `replyToken` 進行一次性即時回覆（Reply Message 完全免費）**。
- **限制**：若 AI 回答超過時效（Reply Token 過期）或需要後續跟進，**嚴禁**轉為非同步 Push 發送；改為留存工單並回覆一次性提示，告知用戶轉入真人客服待辦或引導開啟客服 LIFF。

### 2.5.3 額度防禦支柱三：群組通知取代終端用戶多重 Push

1. **Match_Success 媒合成功**：客戶確認接受後，向唯一啟用的「工會管理群組」發送 1 則 Flex 卡片通知，由工會專員接手線上簽約。
2. **Zero-Pool 拒絕降維**：客戶回覆無法調整條件時，向「工會管理群組」推播人工介入協調卡片。
3. **成效**：大幅減少對終端用戶的付費 Push 則數，集中由工會群組協調處理。

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
- 確認 public base URL 是 HTTPS。
- 確認手機測試帳號目前沒有不需要的舊 binding；有的話先走正式 revocation。

### 手機操作與 4 大分支驗證

1. 點 Rich Menu【服務登記】開啟 `gateway.html`。
2. **分支 1（未申請市府平台）**：點選「未申請市府平台」➔ 彈窗提醒後外連新竹市政府到宅月子媒合服務平台。
3. **分支 2（已申請市府平台 ➔ 身分先行 bind.html）**：
   - **【狀態 A：舊客完全命中】（✅ MOBILE_PASS 2026-09-07 驗收通過）**：
     - 輸入測試客戶 1：姓名：`陳雅婷`、手機：`0912345678`
     - 預期效果：系統自動完成綁定，顯示案件編號【`115000101`】（9 碼查詢序號），提示無需重填問卷，回到聊天室直接啟用【客戶專屬選單】。
     - **實測結果**：手機實測通過，點擊送出後直接成功綁定並帶出案號，無需重填問卷。
   - **【狀態 B：有案號但缺問卷】（✅ MOBILE_PASS 2026-09-07 驗收通過）**：
     - 輸入測試客戶 3：姓名：`李詩涵`、手機：`0933111222`
     - 預期效果：系統識別已向市府申請並取得案號【`115000999`】但尚未填寫工會需求問卷 ➔ 彈出提示「已為您找到案件編號【115000999】，即將無縫載入需求調查表單...」➔ 自動跳轉 `register.html`，頂部提示已連結案件編號，鎖定姓名與電話，由產婦填寫完整 60 題需求問卷後一鍵送出！
     - **實測結果**：手機實測通過，自動預填案號與個資，Email 欄位必填檢核生效，一鍵送出後直接建立完整登記資料與綁定。
   - **【狀態 C：名冊未同步 / 查無案號】**：
     - 輸入全新訪客（例如姓名：`王小明`、手機：`0988776655`）
     - 預期效果：系統提示「市府名冊同步中，即將無縫載入工會需求調查表單...」➔ 自動預填姓名+電話無縫跳轉 `register.html` 填寫需求問卷送出建立臨時登記，後續名冊匯入時自動比對案號。
   - **【狀態 D：連續失敗協處】**：
     - 連續輸入格式錯誤或查核失敗 2 次 ➔ 自動於 `customer_service_tickets` 建立客服協處工單。

### Current 技術路徑

```text
POST /api/v1/line/identity/flow/open
POST /api/v1/line/identity/customer/preview
POST /api/v1/line/identity/customer/apply
```

LIFF 使用 `liff.getIDToken()`；不得由前端任意指定真實 LINE User ID。

---

## M1-02 需求調查表 一鍵送出與防呆檢核

### Agent 前置

- 確認 `register.html` 支援 Email、姓名、電話、地址、服務天數等必填防呆檢核。
- 支援一鍵直接送出（背景自動完成 Preview ➔ Apply，免去手動二段確認）。

### 手機操作

1. 從 M1-01 分支進入 `/line-registration`。
2. **防呆檢核測試**：故意留空 Email 或輸入錯誤手機/Email 格式 ➔ 確認 UI 即時紅字提示阻擋。
3. **正確填寫**：填寫完整資料（Email 必填、姓名、電話、地址等）並完成需求調查。
4. **一鍵送出**：點擊「送出需求調查表」➔ 系統背景自動完成 Preview ➔ Apply 交易，直接顯示成功畫面！

### Current API

```text
POST /api/v1/line/identity/registration/preview
POST /api/v1/line/identity/registration/apply
```

### 驗收

- UI 自動驗證 Email 必填與格式。
- 背景完成 Preview ➔ Apply 流程，直接建立客戶與登記紀錄。
- LINE 聊天室收到登記成功確認推播。

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

# 5. 模組二：專屬客服問答 LIFF、AI 智慧檢索、真人客服與 Feedback 閉環

> 模組二已全面重構為「客服問答專屬 LIFF 頁面」與「聊天室真人專員回覆」分工架構。常規知識庫查詢與 AI 語意檢索由專屬 LIFF 承接（完全不消耗 LINE Push 付費額度）；LINE 官方帳號聊天室則作為真人客服 1 對 1 免費互動空間，AI 不在聊天室搶答。

## M2-01 圖文選單導流驗證（常見問答與 AI 智慧問答）

### Agent 前置

- 確認 `config/line_menu.json` 中訪客選單 (`default_menu`) 與客戶選單 (`customer_menu`) 下方兩格均已配置為：
  - 左下角：【常見問答】（URI 動作 `?target=faq`，`uri_source=liff`）
  - 右下角：【AI 智慧問答】（URI 動作 `?target=ai_assistant`，`uri_source=liff`）
- 確認 Gateway 導向 `/line-service-help`。

### 手機操作

1. 打開 LINE 官方帳號聊天室，呼叫圖文選單。
2. 點選左下角【常見問答】按鈕，檢查是否成功開啟 LIFF 頁面並預設停留在「常見問答」分頁。
3. 關閉後重新點選右下角【AI 智慧問答】按鈕，檢查是否成功開啟 LIFF 頁面並預設停留在「AI 智慧問答」分頁。

### 驗收

- 兩顆按鈕皆為 URI / LIFF 觸發，不發送任何 message 或 postback 扣費事件。
- LIFF 頁面正確載入，標題為「新竹市月子工會 - 服務諮詢中心」。
- 依照點選按鈕正確切換對應初始 Tab。

---

## M2-02 常見問答 (FAQ) 分類與 AI 提問引導橫幅

### 手機操作

1. 在「常見問答」分頁中，點擊頂部分類標籤（如：服務內容與時數、收費與政府補助、服務變更與請假等），檢查列表篩選是否正常。
2. 點擊任一問題（如「月嫂每天的服務時數有哪些選擇？」），檢查解答是否平滑展開顯示，並包含依據規範。
3. 滑動至常見問答列表最下方，檢查是否顯示醒目引導卡片：
   `💡 沒看到您想問的問題？歡迎試試看我們的 AI 智慧問答！輸入您的口語提問，由 AI 助理為您即時檢索工會知識庫標準解答。`
4. 點擊卡片上的【👉 立即體驗【AI 智慧問答】】按鈕。

### 驗收

- 分類標籤點選能即時過濾 FAQ，搜尋關鍵字亦能即時比對問題與內文。
- 解答折疊/展開動畫流暢，內文呈現清晰易讀。
- 列表下方顯眼引導卡片能正確呈現，點擊按鈕後立即平滑切換至「AI 智慧問答」分頁並自動聚焦於提問輸入框。
- 底部顯示真人客服備註：「💬 如需真人專員協助，您亦可直接於 LINE 聊天室中直接留言打字，工會專員將由真人親自為您服務！」

---

## M2-03 AI 智慧問答 LIFF 檢索 (0 Push 額度消耗)

### 手機操作

1. 於「AI 智慧問答」分頁點選推薦問題標籤（如「新竹市產婦補助如何申請？」），或手動輸入口語化問題（例如：「請問月嫂每天服務幾小時？」）。
2. 按下【提問】送出。
3. 觀察系統檢索動畫與即時回答。

### 驗收

- 送出後顯示載入指示器，並即時完成後端知識庫語意檢索。
- 回答卡片標示「✅ 工會核准標準解答」，顯示標準文字與依據規約。
- 全程採用 HTTP REST API (`/api/v1/line/service-help/ask`) 傳輸，**完全不發送 LINE Push 訊息，LINE 官方帳號 Push 額度消耗為 0**。

---

## M2-04 AI 未支援問題與轉真人客服引導

### 手機操作

1. 於「AI 智慧問答」輸入超出知識庫範圍之特殊問題（例如：「請問如何火星登陸與太空梭維修？」或未收錄的特殊客製條件）。
2. 按下【提問】送出。
3. 觀察系統未命中時之處理。

### 驗收

- 系統安全 fallback，標示「💡 轉專人客服引導」。
- 提示文案包含：
  `抱歉，工會知識庫目前尚未收錄與您提問完全相符的標準解答。👉 歡迎直接在目前這個 LINE 官方帳號聊天室中留言，工會真人客服專員將親自為您詳細解說！`
- 不胡亂編造或輸出幻覺答案。

---

## M2-05 LINE 聊天室真人專員回覆空間

### 手機操作

1. 關閉 LIFF，回到 LINE 官方帳號聊天室主介面。
2. 直接在聊天室中輸入文字留言（例如：「請問我想預約 11 月月嫂，還有名額嗎？」）。
3. 檢查聊天室反應。

### 驗收

- 聊天室內 AI 助理**不再搶答**，亦不發送非同步付費 Push。
- 工會專員登入手機端「LINE Official Account」管理 App，可在該用戶對話中看到留言，並直接以真人免費打字回覆。
- 達成客服諮詢與真人服務兼具、且 LINE 官方帳號推播成本最低化之架構目標。

---

## M2-06 Feedback 閉環（未解決轉真人）

### 手機操作

於問答卡片末尾點擊「未解決」。

### 驗收

- 系統回覆文案必須包含：
  `已收到您的回饋（工單編號：...）。AI 問答系統已暫時關閉，您可以直接在此對話中留下訊息等待真人客服回應。`
- feedback durable readback 可見。
- `unresolved` 正式形成 Customer Service ticket/escalation，而不是只有前端計數。
- 用戶後續在對話中的發言將進入真人客服工單對話鏈。

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

## M3-02B 月嫂履歷推薦卡與客戶決策分支

本案例為原圖核心節點「工會傳送月嫂履歷給客戶確認，客戶點選接受或尋求專人協助」的完整 E2E 驗收流程。

### Agent 前置

1. 準備一筆已完成月嫂意願確認的測試案件（例如 `CASE-2026-M301`），候選月嫂具備姓名、居住縣市、服務時段、技能偏好與證書資訊。
2. 透過工會端 API 發出月嫂推薦與客戶履歷確認卡：
   ```text
   POST /api/v1/matches/plans/{case_no}/{plan_id}/customer-confirmation
   ```
   （由 `customer_profiles_card` / `customer_confirmation_card` 渲染送達）
3. 停在客戶手機收到輪播卡狀態，Agent 不得預先代為點擊 postback。

### 手機操作（帳號 A 客戶端）

1. 打開個人 LINE 對話視窗，查收輪播卡片（Carousel）：
   - 卡片 1～N：月嫂簡介卡（顯示月嫂姓名、居住地、證書、技能、偏好，附「下載履歷 PDF」安全按鈕）。
   - 最後一張卡片：【請確認配對方案】決策卡，附帶兩顆行動按鈕：
     - 按鈕 1：`[接受此配對]` (綠色，postback: `matching:{token}:accepted`)
     - 按鈕 2：`[專人協助／進一步了解]` (藍色，postback: `matching:{token}:contact_requested`)
2. 測試分支 1（專人協助）：
   - 客戶點擊 `[專人協助／進一步了解]`。
   - 手機收到即時回覆確認：「已收到您的配對選擇，工會人員會依流程與您聯繫。」
   - 後台案件狀態轉為 `contact_requested`（顯示「客戶希望進一步聯絡」）。
   - **核心業務不變量**：系統**不得**直接退回待媒合池，亦不得取消候選；由工會專員進行真人致電溝通挽回。若客戶溝通後回心轉意同意，由專員直接推進後續；若客戶堅持不同意，再由專員於後台系統操作手動更換月嫂。
3. 測試分支 2（接受配對）：
   - 客戶點擊 `[接受此配對]`。
   - 手機收到即時回覆確認：「已收到您的配對選擇，工會人員會依流程與您聯繫。」
   - 後台案件決策寫入 `accepted`，觸發後續 M3-04 群組簽約通知。

### 驗收

- 2026-09-14 實測通過：工會端寄送月嫂推薦卡，客戶於 LINE 成功收到輪播卡，並完成點選確認（接受配對／專人協助決策分支均已驗收通過），後台狀態與即時回覆均驗證正常。
- 輪播卡不可超過 LINE Carousel 12 張上限，履歷下載連結必須為有效安全的受控下載 URL。
- 客戶決策卡**嚴格只有 2 顆按鈕**（`[接受此配對]` 與 `[專人協助／進一步了解]`），點擊專人協助時轉由專員介入溝通挽回，不直接退回待媒合池。
- Postback 處理 `contact_requested` 時，資料庫記錄狀態 `contact_requested`，UI 面板正確渲染「客戶希望進一步聯絡」。

---

## M3-03 已聯繫零意願分流與拒絕降維協調

### Agent 前置

準備一筆 current matching package 與**非空且已實際聯繫**的候選池；不得直接 INSERT zero-pool event。初次搜尋結果為零不是本案例，不應產生 LINE 通知。

本案例分成三條完整的分流路徑：

- **分流 1（無條件可協調）**：全員完成或逾時、無人願意，且沒有任何月嫂提出調整條件：不發送訊息騷擾客戶；工會待辦顯示人工跟進，並向唯一啟用的工會群組發送 `【媒合需要人工處理】` Flex 通知。
- **分流 2（有條件協調，客戶同意調整）**：全員完成或逾時、無人願意，但至少有一位提出調整條件：AI 彙整去重後向客戶手機發送協商卡片。客戶點選「可以調整」後，工會端待辦顯示「客戶同意調整，待工會修改」，專員於訂單管理修改條件後重新詢問月嫂。
- **分流 3（有條件協調，客戶拒絕降維）**：客戶於協商卡片點選「無法調整」（保留原條件）：系統**不得**直接退案或卡住，而是立即向工會管理群組發送 `【媒合需要人工處理】` Flex 卡片（標題：「媒合需要人工處理」，內文：「客戶目前無法調整條件，請由工會人員接手處理。」），附帶「開啟待辦工作台」按鈕，由專員人工介入協調。

### 手機操作（帳號 A 客戶端）

1. 有調整條件時，帳號 A 收到替代條件 proposal 卡片。
2. 測試分流 3 時，點擊 `[保留原需求／無法調整]`。

### 驗收

- 拒絕降維時，客戶端不中斷，後端產生 `adjustment_customer_answer` (decision: `cannot_adjust`)。
- Worker 自動於工會管理群組推播 Flex 通知，專員於後台待辦清單可見該案號與「manual_resolution」行動需求。

---

## M3-04 Match Success 群組簽約通知

> 客戶確認接受配對後，由系統向唯一啟用之工會幹部群組推播 `【案件媒合成功通知】`，由工會專員接手線上簽約。

### 設備與群組

- 手機帳號 A（客戶）。
- 工會幹部 LINE 群組（已綁定為單一異常與通知群組）。

### Agent 前置

1. 準備一筆處於客戶履歷確認中的案件。
2. 確認工會幹部群組已設定啟用（`line_alert_notification_targets` target_type='group', enabled=TRUE）。

### 手機驗收

1. 客戶手機 A 於決策卡點擊 `[接受此配對]`。
2. 客戶手機 A 收到一次性回覆：「已收到您的配對選擇，工會人員會依流程與您聯繫。」
3. **工會幹部群組**收到 Flex 推播卡片：
   - 標題：`🎉 案件媒合成功通知`
   - 內文：`案件編號：CASE-XXXX`、`客戶已確認同意配對方案！請工會專員接手進行後續簽約與服務確認流程。`

### 驗收

- 群組通知具備唯一性與冪等保護（`matching-group-success:{case_no}:{plan_id}`），同一決策不重複洗版。
- 工會專員於 Web 後台可直接接續辦理線上合約簽署。

---

# 7. 模組四：管理端、群組告警、客訴與代班財務

本節補正測試方法與已確認的 M4 程式問題；不變更 §0.3 已記錄的手機驗收結果，也不把新增自動化回歸測試當作手機或真 provider 通過。PR #299 記錄的 53 項回歸為 29 項 M4 加上 24 項投遞／好友／客服回歸，執行於 run `34733277249` / job `103659935152`；資料庫／交易／provider 使用替身，部分 adapter SQL 在 SQLite 執行，不證明 MySQL 鎖或完整 M4 閉環。

規格 26 §9 的「請假同意／拒絕與 due-shift rematch」及「M4 alert 群組安全直達審核連結」仍是 required acceptance。以下列出現行可操作路徑與缺少的直接證據；缺口保留 `NOT_RUN`，實際無入口／consumer 時記 `BLOCKED` 並說明原因，不得僅因程式尚未接通而標為 superseded 或 passed。

## M4-01 異常通知群組設定

### Agent 前置

- 確認測試管理員已綁定 LINE，並具 `line.alert.manage` capability。
- `GET /api/v1/runtime/line-alert-targets`，讀取 current target、state 與 opaque version。
- 需要重設時先用正式 reset Preview／Apply，不直接清 DB；同群已啟用而只需驗證重複指令時，不必先 reset。

### 手機操作

由已授權管理員在測試 LINE 群組輸入：

```text
設定異常通知群組
```

驗證「第一次綁定 → 正式 reset 停用 → 在同一群組重新輸入指令」：重新綁定沿用同一筆 target，不建立重複群組紀錄，也不重設原通知門檻。已啟用的同群重複設定不重做 mutation；已處理的舊 Webhook event 重播不得把已停用的群組復活。

若另一個群組已啟用，應回報 `line_alert_group_already_active`，不得自動覆蓋。需要切換時，由管理員先正式 reset 目前群組，再於目標群組送出新的設定指令。多個啟用群組是 `line_alert_group_singleton_violation`，不是任選一群。

### Current owner

管理 API：

```text
GET   /api/v1/runtime/line-alert-targets
POST  /api/v1/runtime/line-alert-targets/group/reset/preview
POST  /api/v1/runtime/line-alert-targets/group/reset
POST  /api/v1/runtime/line-alert-targets/{target_id}/preview
PATCH /api/v1/runtime/line-alert-targets/{target_id}
```

管理 mutation 沿用 expected_version、Preview fingerprint、reason、idempotency_key 與 correlation_id 契約。群組設定指令由已驗簽的 LINE Webhook 進入 `LineOrderGroupApplication`，再委派 `RuntimeAlertTargetApplication.register_group`；不是呼叫舊的 `/api/v1/line/system/alert-group`。

Current persistence owner 為 `line_alert_notification_targets` 等 runtime alert tables。確認 target id、state、前後版本與 receipt／audit；不以舊版 `system_settings.alert_group_id` 作為唯一驗收依據。

---

## M4-02 客訴 → Hold → HIGH escalation → Alert

### Agent 前置

- 確認 alert target 已 ready；一個啟用群組與管理員通知對象可以並存，客服告警優先選取唯一啟用群組。沒有群組時只保留既有單一管理員行為；多個管理員不任選一人。
- 確認 `LINE_PUBLIC_BASE_URL` 或 `BASE_URL` 指向可供手機開啟的本站 HTTPS 位址。缺少／無效設定時會回報 `human_escalation_management_url_unavailable`；catalog「開啟客服系統」缺失時為 `human_escalation_management_entry_unavailable`。URL 格式通過不等於手機可連線，須分別記錄。
- 確認 Customer Service readback 可用，記錄測試帳號是否已有工單或 active hold。已有 active hold 的追加訊息與新客訴 ingress 分開驗收。
- 不先建立假 HIGH escalation。

### 手機操作

在沒有 active hold 的狀態，帳號 A 輸入符合 `complaint.v1` 的明確客訴：

```text
我要客訴：服務態度很差，請協助處理。
```

舊版範例「我要退費，服務態度很差，請主管處理。」不屬於目前固定的客訴詞／前綴，不再用它作為本案例必須產生 HIGH escalation 的正向測試。這不是擴充任意負面情緒辨識；自然轉真人語句的確認流程仍依 M2 契約。

### 驗收

應由 canonical complaint ingress 形成：

```text
complaint
→ automation hold
→ customer_service_tickets / customer_service_escalations
→ masked alert intent
→ LINE delivery task
→ 已驗證身分的手機管理入口
```

- HIGH escalation 必須由 owner 產生，不可由 fixture 預先 INSERT。
- 群組內容需去識別化，並包含本站 `/line-mobile-admin?target=customer_service` 導航。這不是授權 token，進入後仍須驗證管理員身分。
- 已結案工單收到新訊息後，可沿原工單重新進入 handling；新的 escalation 應能完成 claim／handling，而不是 Preview 成功、Apply 卻因僅接受 waiting 而失敗。過期版本仍應拒絕。
- 工會完成客服結案後，客戶應收到恢復 AI 的通知，且 delivery 有 terminal readback。該通知屬於 `customer_service_ticket` 與 ticket id；群組告警才使用 `customer_service_escalation` 與 `escalation:<id>`，兩者不得互相覆寫 outcome。
- 分別記錄工單／hold、群組告警與客戶結案通知結果；收到其中一則訊息不代表整條鏈通過。原本已失敗或結果未知的任務不因更新程式自動恢復，未讀回結果前不得盲目重送。

---

## M4-03 Mobile Admin / Safe Review Link

### Agent 前置

Agent 準備一筆**合法待審 root fact**，例如由正式 profile/rebind flow 建立 pending review；不得直接偽造「已核准」結果。

### 手機操作：已驗證管理入口

1. 從 LINE 告警中的本站連結或選單打開 mobile admin。
2. 完成 LINE 身分與管理員 binding／capability 驗證。
3. 查看去敏摘要/diff，Preview approve/reject。
4. 人工確認後由對應 owner Apply，讀回 receipt。

### Safe Review Link：required acceptance 另列證據

短效一次性 Safe Review Link 與一般 mobile-admin 導航是不同契約。規格 26 §9 / §9.1 的 `R4-SAFE-LINK` 仍要求 alert intent／outbox／task 指向 canonical review target，並在 mobile UI 證明 expiry、replay、revocation、wrong actor 等失敗結果。PR #299 的普通導航與版本回歸測試沒有證明這條完整鏈；本輪該直接流程仍為 `NOT_RUN`，不得改列 optional 或以頁面存在替代。

現行 API：

```text
POST /api/v1/runtime/line-safe-review-links
GET  /api/v1/runtime/line-safe-review-links/{link_id}
POST /api/v1/runtime/line-safe-review-links/{link_id}/redeem
POST /api/v1/runtime/line-safe-review-links/{link_id}/revoke
```

新的 Issue 在同一交易中讀取並鎖定唯一啟用 runtime alert group，將 server-owned `target_id` 與 opaque `current_version` 保存到既有 immutable `issued` event 的 `runtime_alert_target` 欄位。第一次 Redeem 重讀 owner facts並比對該 evidence；body 的數字 `target_version` / `current_target_version` 仍須一致，但不是 runtime owner 的版本，也不是 profile／assignment 等業務 owner 的版本證明。

群組更換、停用或同群重新啟用造成版本變更時，原連結不得首次兌換成功。修正前缺少伺服器版本 evidence 的舊連結須重新簽發，不能猜測或補造 evidence；exact command replay 只讀回已存在 receipt，不產生第二次兌換。此描述不授權實際簽發、撤銷或改變告警設定，測試操作仍依該次明確範圍執行。

### 驗收

- token／actor／capability／target／版本錯誤時 fail closed；連結過期、撤銷與非同命令重播亦須拒絕。
- 實際改變 runtime target 後，以舊頁面原樣提交也不得通過；目標未變時可兌換，同一 idempotency key 可讀回原收據而不重做 mutation。
- Safe Review Link 只處理已定義的 transport／runtime target 邊界；profile、assignment 等業務版本仍由各 owner 的正式 Preview／Apply 檢查。
- 業務 Preview 不應直接寫正式資料；Apply 有 receipt/readback。一般導航、link API 與業務核准各自記錄結果，不能相互替代。

---

## M4-04 月嫂請假與代班

規格 20 §5.3 明定 LIFF intake 只建立 Scheduling 待辦，不直接改正式班表；目前已追到的操作路徑是「月嫂提交待辦 → 工會受理 → 案件行事曆正式排班處理」。這個 owner 邊界並未取消規格 26 §9 的客戶同意／拒絕、通知及 due-shift rematch 驗收。v2.1「原圖自動協調敘述以 current owner-safe 流程取代」欠缺明確取消依據，本版撤回該判斷。

### Agent 一鍵前置

Agent：

1. 建一筆 development test order fixture。
2. 準備 client A、staff A、staff B。
3. 建 current assignment/scheduling root facts。
4. bootstrap 案件架構。
5. 確認 staff A 有可請假的 service day。
6. 核對目前使用者可通過請假受理與正式 `leave-substitution` 端點的既有授權檢查；不可只由 `require_system_admin` 函式名稱推導新的角色／升權需求。
7. 停在「staff A 可從手機提出請假」的狀態，不預先建立代班結果。

### 現行可操作路徑：手機與管理後台

1. staff A 從班表／請假頁面填寫日期與原因，Preview 後確認 Apply；readback 應為 pending 待辦。
2. 工會於請假待辦受理，readback 為 `accepted_for_processing`；這不等於正式排班已變更。
3. 工會完成必要聯繫後，在既有案件行事曆選取原服務日，處理順延或 staff B 代班，Preview 並確認正式 Apply。
4. 正式處理時連結該請假 request id 與版本；成功後待辦成為 resolved，保存代班 receipt linkage，並排入 staff A 的完成通知。

### 仍需證明的客戶決策／通知鏈

規格 26 §9 的「請假同意／拒絕與 due-shift rematch」要求 Scheduling 讀回 leave／availability、notification intent／outbox／task；Agree 經 owner Apply更新 end_date／班表，Disagree 建立 substitute ticket，due-shift rematch 經 fresh Preview／Apply形成相應 readback。

目前 intake 提交／受理本身不建立客戶順延決策卡，PR #299 也未接通這一段。不得在月嫂提交後無條件期待客戶立即收到卡片，但也不得因此刪掉此驗收項。客戶端接收、同意／拒絕、owner receipt、拒絕後 ticket及後續通知逐項保留 `NOT_RUN`；若待測版本沒有可操作入口或 consumer，回報具體 `BLOCKED`。工會人工聯繫與日曆 Apply可證明其自身流程，不能假裝已驗證 LINE 客戶決策鏈。

### Current API 與驗收

```text
POST /api/v1/line/staff-self-service/leave-requests/preview
POST /api/v1/line/staff-self-service/leave-requests/apply
POST /api/v1/line/staff-self-service/leave-requests/{request_id}/query
GET  /api/v1/scheduling/staff-leave-requests
POST /api/v1/scheduling/staff-leave-requests/{request_id}/review
POST /api/v1/orders/{case_no}/leave-substitution/preview
POST /api/v1/orders/{case_no}/leave-substitution/apply
```

Current intake root 為 `scheduling_staff_leave_request_aggregates`，並有 events／receipts。正式 substitution 必須走 Scheduling/Leave owner；確認正式 service-day／assignment 變化、linked request、receipt 與完成通知，不以直接 UPDATE schedule 作為 pass。僅建立或受理待辦而尚未正式 Apply 時，不應期待 Payroll 已產生代班款項。現行路徑與上述尚缺的決策链分開記錄，不把單段成功升格為 M4-04 全項通過。

---

## M4-05 代班後 Payroll / Staff Payables

### Agent 前置

可直接沿用 M4-04 已完成正式代班 Apply 的測試案件；這不代表 M4-04 客戶決策鏈亦已通過。Agent 不得另造假的 payroll result。

Agent 執行 repository-local readback：

1. 檢查 assignment/service-day facts。
2. 確認 M4-04 正式 Leave/Substitution Apply 已完成；該流程本身已委派 Payroll impact writer，不另造 payroll result。
3. 讀取 `staff_obligation_events` / `staff_obligations` 等 current SSOT。
4. 回傳每位 staff 的 obligation lineage；可使用 `GET /api/v1/orders/{case_no}/leave-substitution/{batch_key}/payables-lineage` 核對該正式批次。

### 驗收

- 原月嫂與代班月嫂各自有正確 payable obligation。
- 金額來源可追到 assignment/service facts。
- 不再以舊版泛稱 `payroll_items` 是否有兩列作為唯一驗收。
- 規格 26 §9 要求 Scheduling → Payroll → Staff Payables evidence／anomaly projection 的 exact subject、版本與 owner receipt。只有 typed GET或兩列金額不能代替跨域驗收；本輪未驗證的金額及實際資料鏈仍為 `NOT_RUN`。

---

## M4-06 服務前時間確認與檔期試算

### 業務邊界與不可變量

- **SSOT 邊界**：產婦確認實際服務時間（Actual Service Dates），服務日期由 `order_actual_start_events` 與 `order_actual_start_apply_receipts` 唯一管理（`reconfirm_order_actual_start_route`）。
- **試算與專員協調**：產婦提出實際服務開始時間後，系統後端自動比對月嫂排班行事曆：
  - 若無衝突，工會專員於 Web 後台直接確認實際服務起日。
  - 若有衝突，系統產出衝突警告通知工會專員，由專員人工致電協調或調度代班。

### 驗收

- 系統不建立未授權的推播訊息。
- 實際服務開始日異動由正式 `actual_start` writer 執行並留存 before/after 與 Apply receipt。

---

# 8. Agent 快速前置 Prompt 範本

## 8.1 任一案例

```text
請替我準備 LINE 手機測試案例 <TEST-ID>。
限制：只能使用 development/test 環境，不觸發 production，不替我執行手機上的最終決策。
先確認本次待驗證 Git ref 與實際執行版本，再讀該版本的 owner/API/schema；能用 Preview/Apply 就不能直接 SQL。
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
停在 staff A 可以從 LINE 送出請假申請的狀態，回傳月嫂手機、工會受理及案件行事曆正式處理各自的操作與 readback 點。
另列規格 26 客戶同意／拒絕與通知鏈可執行的入口和證據；尚未接通時標 NOT_RUN/BLOCKED，不以人工聯繫代替該項通過。
```

## 8.4 重用單一 LINE 帳號

```text
請替我把目前測試 LINE 帳號安全重置給下一個角色使用。
先讀 current binding，走 revocation preview/apply 與 Rich Menu reset；禁止直接 DELETE line identity binding。
完成後回傳 binding/current-fact readback 與是否已恢復 default menu。
```

## 8.5 M3-02B 客戶月嫂履歷推薦卡與決策

```text
請替我準備 M3-02B 客戶月嫂履歷推薦卡手機實測。
建立一筆 development 測試案件與已完成意願調查的月嫂候選人，包含姓名、技能、證書與履歷。
透過正式端點 POST /api/v1/matches/plans/{case_no}/{plan_id}/customer-confirmation 送出履歷推薦卡。
停在客戶手機即將收到輪播卡與兩顆按鈕的狀態，回傳手機測試包。
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
M2 確定性指令 / 真人客服 / Feedback 閉環
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
→ M3 match success 群組簽約通知
→ M4 staff leave／工會受理／案件行事曆 substitution
→ 客戶同意／拒絕及通知鏈另依 M4-04 缺口記錄，不自動視為通過
```

這樣不需要為每個案例重新人工建立訂單或手動改資料庫；Agent 應先把案件準備到「手機下一步就能操作」的狀態。

---

# 11. Current route／owner 關鍵對照表

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
| QA catalog | `GET /api/v1/knowledge/items?limit=500` |
| Real M2 test | `POST /api/v1/line/ai-events/semantic-test` |
| Gemini status/test | `/api/v1/system/llm/api-key/status`, `/connection-test` |
| Matching readback | `GET /api/v1/matching/coordination/cases/{case_no}/readback` |
| Matching operations | `/criteria/*`, `/criteria-diff/*`, `/caregiver-willingness/*`, `/zero-pool/*`, `/customer-decision/*`, `/conversion/*` |
| Case architecture bootstrap | `/api/v1/cases/{case_no}/architecture-bootstrap/*` |
| Alert target | `/api/v1/runtime/line-alert-targets`；同群重新啟用見 M4-01 |
| Safe Review Link | `/api/v1/runtime/line-safe-review-links`；首次簽發／兌換重驗 runtime group owner，與普通導航分開驗收 |
| Customer Service | current `customer_service_tickets` + escalation owner |
| Leave intake root | `scheduling_staff_leave_request_aggregates` + events／receipts |
| Formal leave/substitution | `/api/v1/orders/{case_no}/leave-substitution/preview`、`/apply` |
| Payroll SSOT | `staff_obligations` / `staff_obligation_events` 等 current Payroll owner |

---

## 文件維護規則

- 此文件描述的是 **current 可操作測試方法與尚缺的 required acceptance evidence**，不是保存舊版 API 的歷史文件；尚在 PR 的修正依文件版本註記核對，不推定 main 或測試環境已更新。
- main 若修改 route/schema/owner，應同步更新此手冊。
- Eraser 原始業務流程及有效驗收以正式基線保存。只有最新明確指示或正式契約已取代原要求時才標 superseded；實作缺漏、普通導航、人工聯繫或局部測試通過，都不構成取消原驗收的依據。失效 API 應修正為現行入口，無入口的要求保留缺口，不要求測試者呼叫虛構 API。
- 禁止在此手冊寫任何 API Key、LINE Channel Secret、access token、管理員真密碼或 production credential。
