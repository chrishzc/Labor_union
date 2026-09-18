# LINE 四大模組詳細測試手冊與 Agent 前置條件規範

> **文件版本**：v2.8（2026-09-18，分離人工／實機驗收與程式驗收；#313、#314 僅追蹤程式測試，真人／手機／provider 可見效果集中於本手冊）
> **原始對齊程式版本**：`main @ 0988f6c430472343662aa1f8989ab2af9732bde3`；包含 PR #299 及後續對齊修訂。開始測試前須確認實際執行版本已包含修正，PR 存在不等於 main 已合併或環境已部署。
> **適用範圍**：LINE 官方帳號、LIFF、Rich Menu、LINE OA 與 React 管理介面的人工／手機／provider 驗收；FastAPI、MySQL、owner/readback 只作人測前置或證據背景，#313／#314 的程式 acceptance 留在 Issue。
> **權威依據**：`document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`、同目錄現行正式規格及其後續修訂；最新明確使用者決定優先。M3-04 幹部群簽約通知、Zero Pool 幹部群告警、M4-01 告警群與 M4-03 告警 Safe Review Link 已取消，不得因舊手冊或舊實作恢復。
> **目的**：本手冊集中記錄真人／手機／provider 可見效果的驗收步驟。Agent 段落只負責準備人測前置資料與測試包，不承擔 #313／#314 的程式驗收；程式、DB、owner receipt/readback 的 acceptance 留在對應 Issue。

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

### 0.3 人工驗收與程式驗收分工（2026-09-18）

自本版起，#313、#314 與本手冊採明確分工：

- **本手冊**：只把需要真人操作 LINE／LIFF／Rich Menu／LINE OA，或需要真人確認 provider 實際送達與畫面效果的項目視為 acceptance。
- **Issue #313、#314**：只追蹤可由程式、owner contract、DB、receipt、task、intent、state transition 與 deterministic readback 驗證的項目；`MOBILE_PASS`／`PROVIDER_PASS` 不再是這兩個 Issue 的結案條件。
- 本手冊既有 **Agent 前置** 只代表準備測試資料、版本、帳號、案件與 readback；前置成功不等於程式流程通過，也不把程式 acceptance 重複搬回本手冊。
- 人工驗收只判斷人能直接觀察的結果；去重、晚到事件、absence of task、DB lineage、transaction、replay、owner state 等不可見條件，由 Issue 的程式測試負責。

#### 從 #313 移入的人工／provider 驗收

| 人測代碼 | 真人操作 | 人工可見通過條件 |
|---|---|---|
| `H313-01` | 在測試版本以新帳號首次加好友；再封鎖後重新加好友 | 兩次有效 follow 都能立即看到現行歡迎訊息與可用身分／服務入口。不要等待或驗收已取消的 D+1／D+2／D+3。 |
| `H313-02` | 在程式測試已證明訂金確認通知 task 可達後，以測試案件完成一次正式訂金確認 | 目標 LINE 帳號實際收到目前有效的訂金確認通知，內容與對象正確；是否去重與 task lineage 不由肉眼判定。 |
| `H313-03` | 僅在 current rule/config 明確啟用訂單生命週期或服務完成通知時執行 | 真人只確認實際送達與顯示內容。若 current disposition 為停用／無 rule，**不為驗收自行啟用**。 |
| `H313-04` | 將測試客戶最後一個 active case 走到 terminal，再重新開啟 LINE OA | 使用者看到恢復後應有的身分／Rich Menu 狀態；此流程不要求額外文字訊息。 |
| `H313-05` | 在測試環境完成月嫂退役流程後，以該月嫂帳號重新開啟 LINE | 原有 staff 權限／選單不可再使用；若 current spec 有既有個人通知，再確認實際送達。 |
| `H313-06` | 以需要人工審核的身分重綁案例執行拒絕／結果通知 | 使用者能看到 current rejection/result 訊息與正確下一步。replay、失敗分類與 receipt 由 #313 程式測試負責。 |

#### #314 的人工驗收歸屬

- `M2-01～M2-05`：沿用本手冊下方手機步驟，驗 Rich Menu → LIFF 導流、FAQ/AI 畫面、unsupported／故障可見差異與 LINE OA 真人回覆空間。
- `M4-02`：只驗客訴／明確轉真人、客服接手／結案與客戶恢復後的可見效果；**群組告警已取消，不是人工驗收條件**。
- `M4-04／M4-05`：真人只操作請假、工會受理與需要人工確認的 UI；Scheduling／Payroll／Staff Payables readback 留在程式 Issue。
- `M4-06`：真人確認實際服務日期入口及工會人工協調入口；衝突試算與 owner receipt 留在程式 Issue。
- `M4-07`：真人建立普通三方服務群組、輸入群組指令、查收邀請卡、加入／退出群組並確認可見狀態；後端 binding／participant／event readback 留在程式 Issue。
- 已取消的 **M3-04 幹部群簽約通知、M4-01 告警群設定、M4-03 告警 Safe Review Link** 不再做人測，也不得為驗收重新啟用。

### 0.4 目前實測執行進度總表（持續更新）

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
| **M3-03** | Zero Pool 協商與拒絕降維 | `REPO_LOCAL_PASS / MOBILE_PASS` | 2026-09-13 | ✅ 歷史手機流程已驗證；其中幹部群告警已由後續使用者決定取消，不需再做人測。 |
| **M3-04** | Match_Success 幹部群簽約通知 | 不適用（已取消） | 2026-09-18 | 已取消群組通知，不再列為人工驗收，也不得為測試恢復。 |
| **M4-01** | 異常通知群組設定 | 不適用（已取消） | 2026-09-18 | 已取消群組告警，不再列為人工驗收。 |
| **M4-02** | 客訴／轉真人 → Hold → Customer Service → 恢復 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-18 | ⏳ 待人測：明確客訴／轉真人、客服接手與結案、後續訊息及客戶恢復後的可見效果；群組告警排除。 |
| **M4-03** | 告警 Safe Review Link | 不適用（已取消） | 2026-09-18 | 已隨群組告警取消，不再做人測。 |
| **M4-04** | 月嫂請假與代班協調 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：月嫂提出請假待辦，工會受理並於案件行事曆完成代班排班。 |
| **M4-05** | 代班後 Payroll / Staff Payables | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：Scheduling 代班排定後自動投影 Payroll 責任分拆，薪資可追溯至排班事實。 |
| **M4-06** | 服務前時間確認與檔期試算 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-13 | ⏳ **待測**：產婦確認實際服務時間（Actual Service Dates）；月嫂排班檔期由系統自動試算衝突並直接通知工會專員人工協調。 |
| **M4-07** | 三方服務群組綁定與邀請發送 | `REPO_LOCAL_PASS / PREPARED` | 2026-09-15 | ⏳ **待測**：工會人員於服務群組輸入「綁定訂單 <案號>」完成綁定；輸入「發送邀請連結 <網址>」自動向媽媽與月嫂私訊推播 Flex 邀請卡；成員加入自動更新為 active；後台可即時回讀。 |

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
- **LINE 測試群組**：只有 M4-07 普通三方服務群組的人測需要可加入官方帳號的測試群組；已取消的告警群不再準備。

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

## M3-04 Match Success 幹部群簽約通知（已取消）

此群組通知已由後續使用者決定取消以節省額度。它不是待測、deferred 或 blocked；本手冊不再提供手機操作步驟，也不得為驗收重新啟用。客戶接受配對後的既有個人／業務流程若仍有效，依其各自條款驗收，不以幹部群收到通知作完成前提。

---

# 7. 模組四：管理端、客訴、代班財務與三方服務群組

本節的人工作業只保留目前仍有效且需要真人觀察的流程。群組告警及其 Safe Review Link 已取消；程式／DB／owner readback 驗收由 #313、#314 或其引用 Issue 追蹤，不以本手冊的人測取代。

## M4-01 異常通知群組設定（已取消）

使用者已取消群組告警以節省額度。本項不再進行手機驗收，不建立／切換告警群，也不因舊程式、設定或測試仍存在而恢復。

---

## M4-02 客訴／明確轉真人 → Hold → Customer Service → 結案恢復（非群組告警）

### Agent 前置

- 準備一個沒有 active hold 的測試帳號與可讀回 Customer Service 狀態的測試案件。
- 不預先建立 ticket、hold 或 escalation 結果；程式端 owner/state/readback 驗收留在 #314。
- 若要驗自然語句轉真人，先確認目前版本使用的確認流程與入口，不擴張成任意負面情緒辨識。

### 手機操作

1. 在 LINE OA 以明確客訴或 current 支援的轉真人語句觸發客服流程。
2. 確認使用者端看到「已轉由真人／客服處理」的 current 可見狀態，不再由已取消的聊天室 AI 搶答。
3. 由合法客服人員接手後，再從同一使用者送一則後續訊息，確認仍延續原客服案件的可見互動。
4. 完成合法結案後，確認使用者收到目前既有的個人恢復通知（若 current flow 有此通知），並可回到正常服務入口。

### 人工驗收

- 真人只判斷 LINE 端是否進入正確的「轉真人／處理中／結案恢復」可見流程。
- ticket id、hold、owner、replay、state transition、receipt、後續訊息是否寫入原案件等由 #314 程式測試/readback 判定。
- **不要求、也不測試任何幹部群告警、告警卡或群組管理連結。**

---

## M4-03 告警 Safe Review Link（已取消）

此項原本依賴群組告警。群組告警已取消，因此本手冊不再做人測，不簽發或兌換告警用 Safe Review Link，也不將它視為待補 acceptance。

一般管理頁面或其他獨立業務審核若仍有有效規格，依其自身流程驗收，不以本項恢復。

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

## M4-07 三方服務群組綁定與邀請發送（Order Group）

### 業務場景與架構定位

- **三方服務群組定位**：案件媒合成功並完成簽約後，工會專員為該案件建立「專屬三方服務群組」（工會專員 + 產婦客戶 + 服務月嫂）。官方帳號（Bot）受邀入群作為訊息轉發與服務協調中樞。
- **與已取消告警群之區隔**：M4-01 告警群已取消；M4-07 是仍有效的普通三方服務群組，一案一群組（1 Order : 1 Group），透過「`綁定訂單 <案號>`」與「`發送邀請連結 <網址>`」執行案件關聯與各別私訊邀請，不得把兩者混用。
- **身分權限嚴格防呆（fail-closed）**：
  - 群組指令僅限已在系統中完成 LINE 身分綁定且具備 `order_group.bind` 能力（如 `line_agent`, `line_manager`, `system_admin`）之工會人員執行。
  - 非工會人員或未綁定帳號在群組發言，系統一律安全拒絕，防止未授權操作。
- **個人化 1 對 1 Flex 邀請卡推播（零個資廣播）**：
  - 專員於群組發送邀請指令時，系統不會在群組中公開 @ 任何人或廣播敏感資訊，而是由訂單受眾事實（`OrderLineAudience`）自動取得案件媽媽與月嫂的個人 `line_user_id`。
  - 系統分別向媽媽與月嫂的「個人 1 對 1 官方帳號聊天室」推播專屬稱謂之 Flex 邀請卡（媽媽收到「媽媽您好…」、月嫂收到「月嫂您好…」），內嵌綠色【加入服務群組】按鈕。
- **群組成員監聽與狀態自適應晉升**：
  - 系統監聽 LINE Webhook `memberJoined` 與 `memberLeft`。
  - 成員加入群組時，更新參與者狀態為 `joined`；當案件之媽媽與月嫂皆加入群組時，群組狀態自動由 `inviting` 晉升為 `active`（活躍中）。
  - 若任一關鍵成員離群，群組狀態自動轉為 `attention`（需注意），提示專員介入關心。

### 設備與帳號角色準備

- **測試帳號組合**：
  - **帳號 A（工會專員）**：已綁定工會幹部身分，於 LINE 建立測試群組並將官方帳號拉入群組。
  - **帳號 B（產婦/媽媽）**：已綁定測試案件之客戶身分（`customer_line_user_id`）。
  - **帳號 C（月嫂/服務人員）**：已綁定測試案件指派之月嫂身分（`staff_line_user_ids`）。
  - *註：若測試者手邊僅有 1～2 支手機，可由 Agent 前置將同一測試帳號或模擬帳號註冊於案件受眾名冊中，同樣能完整驗證指令分發、Flex 私訊發送與後台回讀。*
- **LINE 測試群組**：
  - 建立一個新的 LINE 群組（群組名稱建議標記案號，例如：`心愛月嫂服務群-CASE-2026-M301`）。
  - 將 LINE 官方帳號加入該群組。

### Agent 一鍵前置任務

Agent 在 development/test DB 執行前置檢查與準備：

1. **檢查案件與受眾事實**：
   - 確認測試案號（如 `CASE-2026-M301`）存在且狀態非 `訂單取消`。
   - 確認 `clients.line_user_id` 與 `line_identity_role_bindings`（`subject_type='customer'`、`binding_status='bound'`）存在。
   - 確認該案件有指派月嫂（`case_staff_assignments` 或 `orders.staff_id`），且該月嫂之 `staff.line_user_id` 與 `line_identity_role_bindings`（`subject_type='staff'`、`binding_status='bound'`）存在。
2. **檢查操作者權限**：
   - 確認測試帳號 A 的 `line_user_id` 已綁定工會角色（`subject_type='admin'`），且具備 `order_group.bind` 權限。
3. **檢查群組綁定初態**：
   - 查詢 `line_order_group_bindings`，確認該案號目前處於可綁定狀態（若有舊測試資料，確認 `aggregate_version` 或由 Agent 進行安全重置）。
4. **回傳手機測試包**：案號、操作者 LINE ID、客戶 LINE ID、月嫂 LINE ID、合法邀請連結範例。

### 手機操作與群組指令（真人驗收 4 步驟）

#### 步驟 1：工會人員於 LINE 群組輸入「綁定訂單」指令

工會人員（帳號 A）在剛建立且已拉入官方帳號的 LINE 測試群組中打字輸入：

```text
綁定訂單 CASE-2026-M301
```

> **預期系統即時回覆（群組內）**：
> ```text
> 已將本群組綁定訂單 CASE-2026-M301。請再輸入「發送邀請連結 LINE群組網址」。
> ```

- **底層驗證點**：
  - 系統在單一交易中寫入 `line_order_group_bindings`（`binding_status = 'bound'`，`group_id` 記錄為該群組 ID）。
  - 同步案件受眾名冊至 `line_order_group_participants`（媽媽與月嫂的 `invitation_status` 設為 `pending`）。
  - 寫入事件至 `line_order_group_binding_events`（`action = 'bound'`）。

#### 步驟 2：工會人員於 LINE 群組輸入「發送邀請連結」指令

1. 工會人員於 LINE 群組右上角選單 → 點擊「邀請」→ 點擊「邀請網址」→ 複製群組專屬邀請網址（格式例如：`https://line.me/R/ti/g/abcdef12345`）。
2. 在該群組中打字輸入：

```text
發送邀請連結 https://line.me/R/ti/g/abcdef12345
```

> **預期系統即時回覆（群組內）**：
> ```text
> 訂單 CASE-2026-M301 的邀請已排入發送，共 2 位。
> ```

- **底層驗證點**：
  - 系統驗證邀請網址符合官方安全性規則（必須為 `https://line.me/R/ti/g/...` 或 `https://line.me/ti/g/...`，禁止無關 query parameters 或外部域名）。
  - 系統更新 `line_order_group_bindings` 狀態為 `inviting`，更新 `last_invitation_at_utc`。
  - 寫入執行期事件至 `line_order_group_runtime_events`（`event_type = 'invitation_relayed'`），記錄 64 碼 `invitation_fingerprint`。
  - 系統將兩筆個人發送任務排入 `line_delivery_tasks`。

#### 步驟 3：產婦（媽媽）與月嫂查收個人 LINE 私訊 Flex 邀請卡

分別開啟媽媽手機（帳號 B）與月嫂手機（帳號 C）的 LINE 官方帳號 1 對 1 聊天室：

- **產婦（媽媽）手機畫面**：
  - 收到 Flex 卡片，標題為【**服務群組邀請**】。
  - 內容顯示：
    - `案件編號：CASE-2026-M301`
    - `媽媽您好，請點下方按鈕加入本案服務群組。`
  - 底部綠色按鈕：【**加入服務群組**】。
- **月嫂手機畫面**：
  - 收到 Flex 卡片，標題為【**服務群組邀請**】。
  - 內容顯示：
    - `案件編號：CASE-2026-M301`
    - `月嫂您好，請點下方按鈕加入本案服務群組。`
  - 底部綠色按鈕：【**加入服務群組**】。

#### 步驟 4：成員加入群組與狀態自適應晉升（`active`）

1. 媽媽（帳號 B）點擊【加入服務群組】按鈕，手機開啟 LINE 群組並點選「加入」。
2. 月嫂（帳號 C）點擊【加入服務群組】按鈕，手機開啟 LINE 群組並點選「加入」。
3. **驗證結果**：
   - 官方伺服器接收 LINE Webhook `memberJoined` 事件。
   - `line_order_group_participants` 更新各成員的 `invitation_status = 'joined'` 與 `joined_at_utc`。
   - 當名冊內的所有參與者（媽媽與月嫂）皆已完成加入（`invitation_status <> 'joined'` 計數為 0）時，系統自動將 `line_order_group_bindings.binding_status` 晉升為 `active`，並記錄 `activated_at_utc`！

### 異常防呆與錯誤提示驗收（7 大防呆分支）

| 情境 | 操作與輸入 | 預期系統安全回覆 / 結果 | 防呆驗證要點 |
|---|---|---|---|
| **分支 A：非工會人員發言** | 一般客戶或未綁定身分之帳號在群組輸入 `綁定訂單 <案號>` | `此操作只允許已綁定 LINE 的工會人員使用。` | 嚴格防禦未授權發送者任意綁定案件。 |
| **分支 B：查無案件** | 輸入不存在之案號，如 `綁定訂單 NON-EXIST-999` | `找不到指定訂單。` | 查無 Orders 根事實即刻 fail-closed。 |
| **分支 C：訂單已取消** | 輸入狀態為 `訂單取消` 之案號 | `已取消的訂單不能綁定服務群組。` | 已終止/取消案件禁止再建服務群組。 |
| **分支 D：未綁定即發邀請** | 在尚未執行綁定之新群組直接輸入 `發送邀請連結 <網址>` | `本群組尚未綁定訂單，請先輸入「綁定訂單 案件編號」。` | 必須先有 case binding 才能派送邀請。 |
| **分支 E：受眾尚未綁定 LINE** | 案件之媽媽或指派月嫂尚未綁定 LINE（查無 `line_user_id`） | `訂單的媽媽或月嫂尚未完成 LINE 綁定。` | 避免邀請發送進入黑洞，促使專員先引導綁定。 |
| **分支 F：非法邀請網址格式** | 輸入外部網址（如 `https://google.com`）或帶 query 之網址 | 系統安全攔截驗證錯誤，不發出無效推播。 | 嚴格比對 `https://line.me/(R/)?ti/g/[^/?#]+`。 |
| **分支 G：群組重複綁定衝突** | 在已綁定訂單 A 的群組再次輸入 `綁定訂單 <案號B>` | `此群組已綁定其他訂單。` | 一個 LINE 群組僅限綁定單一有效訂單。 |

### React 管理後台回讀核對

1. **清單與狀態核對**：
   - 登入工會管理後台 → 進入【**LINE 管理**】→ 切換至【**三方服務群組**】Tab（`line.tab.order-groups`）。
   - 表格中應正確列出 `#{case_no}`，且群組狀態標籤應依步驟顯示 `已綁定 (bound)` → `邀請中 (inviting)` → `活躍中 (active)`。
   - 支援分頁（numbered query：`page`、`pageSize`、`total`、`totalPages`），前端不進行假切片。
2. **Drawer 明細與歷程核對**：
   - 點擊該列「**查看明細**」開啟側邊抽屜（Drawer）。
   - 核對內容：
     - **基本資訊**：案件編號、LINE 群組 ID、當前狀態標籤。
     - **事件歷程**：時間由新至舊依序列出 `member_joined`、`invitation_relayed`、`bound` 等事件類型與發生時間。
     - **邀請指紋**：歷程中記錄安全的 64 碼 SHA-256 `invitation_fingerprint`，群組邀請之敏感 token 絕不洩漏至日誌或前端。

### Current API / Owner / Schema 對照

- **群組 Webhook 處理**：
  - Ingress：`LineWebhookEventConsumer` → `LineWebhookIdentityHandlers.handle_message` & `handle_group_membership`
  - Owner：`subsystems.line.order_group_application.LineOrderGroupApplication`
  - 網址安全性校驗：`domains.line.order_group._validate_invitation_url`
- **管理端 Query API**：
  - `GET /api/v1/line/order-groups/numbered?status={status}&page={page}&page_size={page_size}`
  - `GET /api/v1/line/order-groups/{case_no}`
  - `GET /api/v1/line/order-groups/{case_no}/events/numbered?page={page}&page_size={page_size}`
- **資料庫 SSOT 表**：
  - `line_order_group_bindings`：記錄案件與 LINE 群組 ID 之一對一綁定關係、狀態（`unbound` / `bound` / `inviting` / `active` / `attention` / `replaced` / `released`）及樂觀鎖版本（`aggregate_version`）。
  - `line_order_group_participants`：記錄案件參與者（`customer` 媽媽、`staff` 月嫂）之 `line_user_id`、邀請狀態（`pending` / `joined` / `left`）與加入時間。
  - `line_order_group_binding_events`：記錄群組綁定與換群事件（`bound` / `replaced`）。
  - `line_order_group_runtime_events`：記錄執行期邀請轉發與成員進出事件（`invitation_relayed` / `member_joined` / `member_left`）。

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

## 8.6 M4-07 三方服務群組前置

```text
請替我準備 M4-07 三方服務群組綁定與發送邀請手機實測。
限制：使用 development/test 環境，不變更 production。
確認已有一筆有效 development 測試案件（如 CASE-2026-M301），且該案件之客戶（媽媽）與指派月嫂（staff）均已在 line_identity_role_bindings 處於 bound 狀態（若單機測試可使用同一組已綁定測試 LINE ID 或前置提供兩組測試 user_id）。
確認執行測試的工會人員帳號已綁定工會幹部身分，並具備 order_group.bind 權限。
檢查 line_order_group_bindings，確認案號尚未被其他群組鎖定或重設為可綁定狀態。
完成後回傳「手機測試包」：case_no、可發送的合法邀請連結範例、工會人員群組下指令步驟、媽媽與月嫂預期收到的私訊內容、以及後台三方服務群組查驗點。
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
| Order group commands | LINE 群組文字指令：`綁定訂單 <case_no>`、`發送邀請連結 <url>` |
| Order group query API | `GET /api/v1/line/order-groups/numbered`、`GET /api/v1/line/order-groups/{case_no}/events/numbered` |
| Order group SSOT | `line_order_group_bindings`、`line_order_group_participants`、`line_order_group_binding_events`、`line_order_group_runtime_events` |

---

## 文件維護規則

- 此文件描述的是 **current 真人／手機／provider 可操作驗收方法**，不是 #313／#314 的程式測試追蹤器，也不是保存舊版 API 的歷史文件；Agent 前置與 readback 僅用來準備人測，不在本文件重複承擔程式 acceptance。
- main 若修改 route/schema/owner，應同步更新此手冊。
- Eraser 原始業務流程及有效驗收以正式基線保存。只有最新明確指示或正式契約已取代原要求時才標 superseded；實作缺漏、普通導航、人工聯繫或局部測試通過，都不構成取消原驗收的依據。失效 API 應修正為現行入口，無入口的要求保留缺口，不要求測試者呼叫虛構 API。
- 禁止在此手冊寫任何 API Key、LINE Channel Secret、access token、管理員真密碼或 production credential。
