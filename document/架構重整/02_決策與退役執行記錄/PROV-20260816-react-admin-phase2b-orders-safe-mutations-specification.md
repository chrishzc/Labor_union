---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase2b-orders-safe-mutations
owner: orders / global-admin-web-presentation
date: 2026-08-16
base_ref: ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922
depends_on:
  - PROV-20260816-react-admin-phase2a-orders-query-real-data
approval_required: exact-phase2b-work-package
---

# React 管理端 Phase 2B：Orders 安全 Mutation 規格

## 1. 狀態與目的

本文件是 `proposed` 規格，不是 production mutation 授權。目標是在不重畫既有 React UI 的前提下，
把目前已鎖定的兩個 Orders 操作接成真正的 server `Preview → Apply → receipt → re-query`：

1. 確認正式服務日期（Confirmed Service Dates）。
2. 受控重啟已取消訂單（Controlled Reopen）。

這兩條能力已有可界定的 typed success view、版本與 fingerprint。其餘按鈕不因「後端有 route」就納入；
任何含 raw `dict` impact、跨 Domain 未 typed、或會把 execution assignment 冒充 formal recommendation
的能力仍 fail closed。

## 2. 人工業務裁決與不變量

本波不得改寫下列已確認語意：

1. 一般正式推薦是一位月嫂；只有 server 證明單一月嫂無法覆蓋全部日期時，才允許 2–4 位分段方案
   作為一個整體正式推薦。Confirmed Service Dates 不選月嫂，也不形成正式推薦。
2. 服務完成、客戶款項結清、月嫂薪資核銷是三個獨立 projection；本波不推導任何一項。
3. 缺緊急聯絡電話只 warning，不阻擋媒合；本波不新增 emergency-contact gate。
4. Query 唯讀、Preview 零寫入；Apply fresh-read、驗證 versions／fingerprint／idempotency 後單次 commit。
5. UI 只有收到 server receipt 才顯示成功；timeout／network unknown outcome 不得 optimistic success。
6. React 不計算 selectable dates、服務日守恆、reopen eligibility、恢復內容或 lifecycle target status。
7. 0 DDL/schema/migration/seed/backfill；只允許透過核准 API 修改明確指定的 disposable/local test case，不得操作既有營運資料。

## 3. Bounded capability A：Confirmed Service Dates

### 3.1 Business scenario

```text
開啟既有日期 Drawer
→ GET current/suggested/selectable dates與versions
→ 操作者只從server selectable set選 contracted count
→ POST Preview（零寫入）
→ 顯示server weeks／dates／versions／fingerprint
→ 操作者確認
→ POST Apply（same draft idempotency key）
→ receipt
→ GET重新觀察current version/dates
```

Confirmed Service Dates 只建立 Orders-owned confirmed dates version，並使舊 matching schedule snapshot
失效；不建立 assignment、staff schedule、Payroll impact、Client Finance impact或 LINE task。

### 3.2 HTTP contract & Header rules

| Operation | Endpoint | Success view | Required request facts | Request Headers |
|---|---|---|---|---|
| Query | `GET /api/v1/orders/{case_no}/service-dates` | `ServiceDateConfirmationQueryView` | case_no | `Authorization` |
| Preview | `POST /api/v1/orders/{case_no}/service-dates/preview` | `ServiceDateConfirmationPreviewView` | exact service_dates | `Authorization`, `X-Correlation-ID` |
| Apply | `POST /api/v1/orders/{case_no}/service-dates/apply` | `ServiceDateConfirmationReceiptView` | service_dates、expected order/scheduling versions、fingerprint、reason | `Authorization`, `X-Correlation-ID`, `Idempotency-Key` |

前端 decoder 必須 strict 驗證 envelope、ISO date、正整數、64 hex fingerprint及 unknown fields。
Apply request 不接受由 React 計算的 weeks、end date、assignment、staff、hours或 lifecycle status。

### 3.3 Required backend hardening & Error boundary

1. 現行 `service_date_confirmation.py` 將 `ValueError` 映射成 raw `detail.code`，且 Apply reason 可空。
   Phase 2B 若核准，backend writer 只收斂 workflow/route 產生的 typed errors 至 Global typed error envelope；
   FastAPI request validation (422) / 401 / 403 列為 `BACKEND_GAP`，不自行擴張 `api/main.py` 或 shared error infrastructure。
2. Apply reason 改為必填、trim 後非空、長度 1–500 字。
3. 保留既有 success response fields 與路徑，不新增 DB/schema。
4. focused route tests 證明 Preview 零寫入、stale conflict、same-key replay 與 error envelope。

## 4. Bounded capability B：Controlled Reopen

### 4.1 Business scenario

```text
點既有「重啟訂單」
→ POST Preview（無 local eligibility猜測）
→ 顯示 before/after、cancellation event、三versions、所有 restored lists應為空、fresh scheduling提示
→ 操作者輸入非空reason（1–500字）並確認
→ POST Apply（preview versions/fingerprint + same idempotency key + correlation id）
→ receipt
→ re-query summary/detail
```

Reopen 追加不可變事件，不刪 cancellation history，不恢復 assignment／schedule／lock／payment stage。
若已有退款、reversal或 settlement，server blocker為權威；React不得依 order status猜允許與否。

### 4.2 HTTP contract & Header rules

| Operation | Endpoint | Success view | Required request facts | Request Headers |
|---|---|---|---|---|
| Preview | `POST /api/v1/orders/{case_no}/reopen/preview` | `OrderReopenPreviewView` | `X-Correlation-ID` | `Authorization`, `X-Correlation-ID` |
| Apply | `POST /api/v1/orders/{case_no}/reopen/apply` | `OrderReopenReceiptView` | expected order/client-finance/payroll versions、fingerprint、reason | `Authorization`, `X-Correlation-ID`, `Idempotency-Key` |

- Preview 驗證三版本 (`order_version`, `client_finance_version`, `payroll_version`)。
- Apply request body 傳入三個 expected versions、`reason`、`preview_fingerprint`。
- Success receipt 僅驗證 live Pydantic 已有欄位：`case_no`、`order_version`、`lifecycle_status`、
  `cancellation_event_id`、`requires_fresh_scheduling_preview`、`preview_fingerprint`；不得自行新增
  `client_finance_version`、`payroll_version`、`created_at` 或其他欄位。
- `X-Correlation-ID` 是 request header，不是 success receipt 欄位。
- 前端必須顯示 `requires_fresh_scheduling_preview`；receipt 後仍不可恢復或生成排班。

### 4.3 Required backend hardening for Reopen

1. `api/routes/order_reopen.py` 的 reason 補上 trim 後非空校驗（禁止純空白字串），長度限制為 1–500 字。
2. 專屬 route tests 覆蓋空字串、純空白、1–500 字及超過 500 字之驗證防護。

## 5. UI 行為（保留既有設計）

### 5.1 日期 Drawer

- 保留原 Drawer、欄位分組、假日槽位、雙方確認槽位與按鈕位置。
- 本波只啟用 confirmed service-date selection／Preview／Apply。
- Actual Start、假日協議、寄送精算日程、電話補登雙方確認、轉正式履約仍 disabled/unavailable。
- Query、Preview、Apply、receipt 是四個可見狀態；Preview後修改日期會使舊preview立即失效。
- Apply pending時 single-flight，Drawer 不可因 backdrop／Escape 靜默丟失 unknown outcome。

### 5.2 Reopen Dialog／Drawer

- 使用現有 order card 的「重啟訂單」位置，不新增第二入口、不以 stage顯示條件猜 eligibility。
- 點擊後才呼叫 Preview；404/409/422/503顯示 typed error與correlation id，不顯示成功。
- Preview顯示 before/after、是否需 fresh scheduling、reason input與明確 Confirm Apply。
- Apply後顯示 receipt；重新查詢成功後才更新卡片資料。

## 6. Idempotency、stale、retry與 outcome_unknown 狀態恢復

- 每個使用者 draft建立一個記憶體 idempotency key；相同payload重試沿用，修改payload後建立新draft key。
- idempotency key、token、correlation id不得進URL、DOM、console、snapshot或versioned receipt。
- 409 conflict：清除 preview，重新Query／Preview；不得自動 Apply。
- 503 retryable與transport timeout：進入 `outcome_unknown` 狀態。
  - `apply_pending` → `outcome_unknown`
  - `outcome_unknown` → `apply_pending`（僅允許相同 payload + 相同 `Idempotency-Key` 重試）
  - `replayed receipt` → `requery_loading` → `observed`
- `receipt_received` 後的 re-query 失敗不是 Apply 結果不明：保留 receipt，進入
  `observation_failed`；此時只能重試 Query，不得重送 Apply。
- `outcome_unknown`、`receipt_received`、`requery_loading` 期間 payload 必須凍結；日期、reason、版本、
  fingerprint 與 idempotency key 均不得改變。正常 Apply 控制也必須 disabled，只保留相同 payload/key
  的專用 replay action。
- Drawer 關閉、切頁或重新 mount 不得遺失該 key；狀態必須保存在 task-owned、memory-only 的 Orders
  flow store，不能只放在 Drawer local state，也不得使用 `localStorage`、`sessionStorage`、URL 或 cookie。
- double-click、tab switch與component remount不得提交兩次。
- Preview request可abort；Apply一旦送出不得把client abort解讀成未提交。

## 7. 明確不納入 Phase 2B

| UI capability | Exclusion reason / successor need |
|---|---|
| Terms Preview／Apply | preview view仍含 raw scheduling/client-finance/payroll/lifecycle dict impacts；先建立 typed impact models |
| Actual Start Preview／Apply | preview view仍含 raw cross-domain impacts；不得用 `z.record`／`unknown`吞掉 |
| Cancellation Preview／Apply | preview view含 raw impacts，且需逐日owner UI；另立 contract-hardening wave |
| Assignment Plan Preview／Apply | raw buffers/impact dict且為execution，不是formal recommendation |
| Contract Completion Apply | 必須由 Contract Signing signed event與outer UoW觸發，不做人工「完成」按鈕 |
| Candidate pool／Info1／Info2／意願／履歷／客戶決策 | current HTTP主要為 `BaseResponse[dict]`；需 Scheduling/Matching typed contract |
| LINE manual replay | 跨 LINE bounded domain，無核准 order-scoped typed timeline |
| 7-stage／11-step status | 無 typed lineage projection |
| 三結清／emergency warning | 無current composite typed query |

## 8. Security、PII與Auth

- 真實 browser acceptance必走 `password challenge → TOTP → Session`，不得使用 localStorage/dev token繞過。
- client每次request即時取得current memory session token，不在module-load快取。
- reason、case_no、receipt只保留必要資訊；完整電話、地址、token、TOTP、銀行資料不得進證據。
- mutation需同權限內部使用者政策與server audit；React不建立role差異。

## 9. Completion definition

只有以下全部成立才可完成：strict contract、Preview零寫入、Apply receipt/replay/stale/rollback tests、
原UI保留、零fake mutation、真兩段式登入瀏覽器Network↔DOM、zero unintended non-GET、Phase2A regression、
lint/build/full tests、backend focused tests與去敏evidence。缺browser credentials時狀態固定為 `BLOCKED_REAL_BROWSER_EVIDENCE`，
缺合法測試案件時為 `BLOCKED_TEST_DATA`，但均不得以此跳過contract/client/page tests。

## 10. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | 本規格禁止 DDL/schema change |
| Change inventory | NOT_RUN | 無 schema/seed/backfill/destructive write set |
| Static release gate | NOT_RUN | 不建立 migration release |
| Descriptor gate | NOT_RUN | 不變更 DB object |
| Read-only plan gate | NOT_RUN | 非 migration 任務 |
| Engine verification gate | NOT_RUN | 不以 UI mutation擴張DB gate |
| Developer acceptance gate | NOT_RUN | 僅透過核准 API 操作 disposable test case，不操作既有營運資料庫 |

總結：`DB_CHANGE_NOT_READY`；Phase 2B 不授權 DDL/schema/migration 或直接資料庫操作，只允許經核准 API
對明確 disposable/local test case 產生本包定義的業務資料寫入。
