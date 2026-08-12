# LINE 客服與月嫂自助服務正式規格

## 1. 文件狀態

- 狀態：`approved-first-release-baseline`
- 人工確認日期：2026-08-11
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 視覺來源：`merge` 分支 Rich Menu、客服及 LIFF 面板
- 執行架構：`wen` canonical LINE inbox、identity、delivery 與 Rich Menu publication

## 2. Global 不變量

1. LINE webhook 只保存 canonical inbox event；業務處理由 consumer 執行。
2. 所有 LINE 回覆皆建立 durable delivery task，不在 webhook 或管理 UI 直接呼叫 LINE。
3. LIFF 正式身分只信任 server-side 驗證後的 ID token 與正式 binding；query string userId 不是身分證明。
4. LINE Integration 不擁有 Orders、Scheduling、Customer Service 或客戶主檔狀態。
5. Rich Menu 圖面與文字可沿用 merge，但 definition、revision、publication 與 per-user binding 仍以 wen DB 為 SSOT。
6. `綁定訂單`、`訂單查詢` 固定進入 customer binding；`綁定後台帳號` 固定進入 admin binding。
   Service Help／Customer Service 不得攔截或重定義這三個既有 identity aliases。
7. `工會選單`、`開啟客服系統`、`月嫂驗證管理` 只接受已 bound 的 admin LINE identity，並透過
   Rich Menu binding outbox 套用 `union_staff_menu`；`esc` 對所有 LINE user 透過同一 outbox
   套用 `default_menu`。兩者都不直接查 legacy role table、直接寫 task 或呼叫 LINE API。
8. 2026-08-12 人工授權 canonical cutover：webhook 與 worker 的未設定預設都是 `canonical`。
   `legacy` 僅可由 webhook／worker 同時明確設為 `legacy`，且 production 必須另設
   `LINE_LEGACY_ROLLBACK_MODE=true` 才能作受控 rollback。

## 3. Customer Service Domain

### 3.1 責任與 SSOT

Customer Service 擁有客服需求、對話事件、處理狀態、處理人與版本。LINE user、client、case 只保存可追溯 reference；正式客戶與訂單資料仍由其原 Domain 擁有。

根事實：ticket ID、LINE user ID、category、client/case reference、原始訊息、status、version、actor、created/updated/resolved time。衍生值包含狀態標籤、今日統計與遮罩顯示值。

### 3.2 狀態機

```text
waiting → handling → resolved
             ↑          │
             └──────────┘ 新訊息重新開啟
```

不允許跳過狀態驗證或以 UI 字串決定 transition。管理 command 必須帶 expected version；stale command 回 conflict。

### 3.3 交易、冪等與 retry

- inbound event：ticket create/append、狀態事件、ack delivery task 同一 LINE Unit of Work commit。
- admin reply：鎖定 ticket、驗證 version、保存回覆、更新狀態、audit、delivery task 同交易 commit。
- inbound idempotency 使用 LINE event ID；admin mutation 使用 caller idempotency key。
- provider timeout/5xx 只 retry delivery task；validation、authorization、stale conflict 不自動 retry。
- retry exhausted 建立 LINE runtime alert，客服資料不得因 provider 暫時失敗回滾。

### 3.4 Typed errors

- `customer_service_ticket_not_found`
- `customer_service_ticket_version_conflict`
- `customer_service_transition_invalid`
- `customer_service_category_invalid`
- `customer_service_delivery_unavailable`

## 4. Service Help Subsystem

精確 intent 為「服務說明」及六分類別名。分派順序固定為 identity、group、service help、knowledge fallback，避免「綁定」或知識問答搶走 intent。

第一版行為：

1. 服務說明：回覆六分類選單。
2. 服務流程、收費與補助：回覆核准文案。
3. 查詢服務進度：只查已綁定客戶最新案件；未綁定則送 canonical 綁定入口。
4. 修改登記資料、聯絡工會人員、其他問題：建立或延續客服需求。
5. 同一 LINE user、同一 category 同時最多一筆未完成 ticket；exact replay 不追加重複訊息。

## 5. Staff Self-Service Subsystem

### 5.1 訂單查詢

以 verified LINE identity 對映 staff subject，再由有效 `case_staff_assignments` 限制可見案件。姓名或案件編號只作該授權集合內篩選，不可擴大權限。

### 5.2 排班查詢

重用 `subsystems.scheduling.staff_monthly_calendar_query`，以 assignment-owned `staff_schedule` 與正式 availability lock 投影。不得新增另一套排班 SQL writer。

### 5.3 請假

第一版不允許 LIFF 直接改正式排班。未來若啟用，只能先建立人工 intake，再由管理員使用既有 Leave/Substitution Preview／Apply；其版本、fingerprint、mutex 與跨 Domain impact 不得省略。

請假審核 API、管理 client 與 UI caller 屬 Scheduling；不得附加到 LINE identity review route
或 `LineAdminApiClient`。LINE Integration 只接受已提交的通知 intent 並回報 delivery outcome。

Typed errors：

- `liff_token_invalid`
- `line_staff_binding_not_found`
- `staff_order_not_visible`
- `staff_schedule_query_invalid`

## 6. UI 與人工入口

- merge 的 Rich Menu 圖面、按鈕標籤與 LIFF 卡片樣式可移植。
- 客戶「已填過／尚未填過」選擇必須保存 canonical flow ID；未填過流程完成登記後才能完成同一 LINE 身分綁定。
- LINE 管理中心使用 Customer Service bounded API client；成功 payload 轉 typed Pydantic view，transport/schema error 轉 typed client error。
- Streamlit 只顯示 typed result 與提交 command，不包含 ticket transition 或 SQL 規則。

## 7. 第一版驗收

1. 服務說明回覆六分類且 exact replay 不重複建立 task。
2. 客服需求可建立、列表、查看、更新、回覆及完成。
3. 客服回覆透過 canonical delivery worker 發送。
4. 偽造 URL userId 無法讀取客戶、月嫂訂單或班表。
5. 月嫂只能讀取自己的有效 assignment 案件與班表。
6. merge Rich Menu 圖面／文案可由 wen publication 流程發布並 fan-out。
7. 客戶前導頁保留 flow ID，兩條路徑都不退回 legacy gateway。
