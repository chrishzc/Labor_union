---
doc_type: decision-required
status: approved-for-implementation
created_at: 2026-08-09
scope: LINE native customer registration writer exit
approved_by: user
approval_date: 2026-08-09
---

# LINE 暫存客戶登記的 Typed Replacement 決策

## 已確認的現況

`POST /api/line/register` 目前會在同一交易中建立：

1. `clients` 的暫存客戶資料（`case_no = NULL`、含 `line_user_id`）；
2. `beclass_records` 的未關聯問卷（`query_no = NULL`）；
3. 一筆 LINE 成功通知任務。

它刻意不建立 `orders`，因為正式案件編號尚未由行政核發。
這不是既有 Case Import：Case Import 的根識別是已存在的 `case_no`，且會
同時建立訂單與後續 bootstrap 事實。因此不能把這個 endpoint 偽裝成 Case
Import，也不能在未決定重送規則時直接退休舊 writer。

## 必須確認的業務決策

LINE/LIFF 表單可能因網路逾時或使用者重按送出而重送；目前每次都會建立新的
`clients` 與 `beclass_records` 列。Typed replacement 必須選擇一個明確規則：

1. **同一 LINE 使用者只能有一筆未核發案件的暫存登記（已採用）**：相同 payload
   重送回傳原 receipt；不同 payload 產生 `registration_conflict`，由行政在待辦中
   核對或明確取代。
2. **同一 LINE 使用者可以反覆送出新登記**：每次送出都是獨立申請，需新增
   `registration_submission` 根事實與穩定 submission id，供之後人工選擇哪一筆
   核發為案件。
3. **以電話號碼作為未核發登記的去重鍵**：必須先確認家人共用電話或更換 LINE
   帳號時的歸屬與合併規則。

## 選項 1 的目標架構

| 層級 | 責任 |
|---|---|
| Global | LIFF 身分驗證後的 `line_user_id` 是送件者；不得以 client id 假定正式案件。 |
| Domain | `ProvisionalClientRegistration` 的根識別為 `line_user_id`；狀態為 `submitted` 或 `case_issued`。 |
| Subsystem | Preview/Apply 以 payload fingerprint 與穩定 idempotency key 管理重送；Apply 在單一交易寫暫存客戶、問卷、receipt 與通知 task。 |
| Module | MySQL repository 用鎖定讀取未核發登記；Case Import 在行政核發 `case_no` 時明確消費該暫存登記，並將問卷關聯到 `query_no`。 |

## 不可變量

- LINE 登記不建立 `orders`、付款、薪資或排班事實。
- `beclass_records.query_no` 僅在行政核發 `case_no` 後設定。
- 通知 task 使用 registration receipt identity 作為 idempotency key；重送不得重複推播。
- 案件核發時，暫存 client、問卷與正式 `case_no` 的合併必須在同一 owner transaction
  內完成，不能由 LINE route 直接寫欄位。

## 已落地範圍與後續合併責任

2026-08-09 已依選項 1 實作 typed provisional registration。它以
`provisional_client_registrations.active_line_user_id` 的唯一鍵保留一筆 active
registration；相同 payload 回傳原 receipt，不同 payload 回傳
`registration_conflict`。舊 LIFF endpoint 保留為相容入口，但不再直接寫
`clients`、`beclass_records` 或 `line_tasks`。

後續 Case Import 核發 `case_no` 時，仍必須實作同一 owner transaction 的消費／
併案動作，將 status 設為 `case_issued` 並清除 `active_line_user_id`；在此之前，
同一 LINE 使用者不能再次建立新的待核發登記。
