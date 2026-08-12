---
doc_type: decision-required
status: completed
declared_status: completed
created_at: 2026-08-09
scope: LINE native customer registration writer exit
approved_by: user
approval_date: 2026-08-09
updated_at: 2026-08-11
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

## 2026-08-11 residual Work Package

### 已完成且不得重做

- 暫存登記 root、active LINE user 唯一鍵、same-payload replay、different-payload conflict；
- 舊 LIFF 相容入口改接 typed application，不再直接旁路寫三張表；
- registration receipt identity 擁有通知 task idempotency。

Fresh focused tests：`tests/test_provisional_line_registration.py`，`4 passed`。

### 唯一剩餘 business scenario

行政透過 Case Import 核發正式 `case_no` 時，系統必須鎖定同一 active provisional registration，
確認 submitted state／payload fingerprint／client／BeClass identities，在 Case Import owning outer
Unit of Work 內建立正式案件根事實、關聯問卷、append `case_issued` event／receipt，並將
`active_line_user_id` 清空。任何 stale、重複 case、registration conflict 或中途失敗皆零 partial
write；same-key replay 回原 receipt。

### Write set 與驗收

- Domain／Subsystem：Case Import provisional-registration consumption command、typed result/errors；
- Infrastructure：additive event／receipt contract（僅在現有 schema 不足時）、repository lock／apply；
- API／UI：沿用 Case Import 正式入口，不新增 LINE route direct writer；
- Tests：Module state transition；Subsystem replay/conflict/rollback；disposable MySQL 驗證
  submitted→case_issued、client／BeClass／Orders roots 同交易、同 key replay 與不同 payload conflict。

本文件之外沒有第二個 provisional registration backlog；完成此 residual 並取得 receipt 後，才可
將本文件改為 `completed`。

## 2026-08-11 可執行規格：Case Import consume／merge

### 1. 業務場景與邊界

行政已核對 LINE 送件資料，並以 Case Import 核發唯一的正式 `case_no`。此時系統必須把
既有 provisional client 升格為該案件的 Client root，建立同一案件唯一的 Order 與 architecture
bootstrap roots，並把既有 BeClass 問卷關聯到正式案件。行政不可另建一筆同資料 client，也不可
由 LINE endpoint 補寫 `case_no`。

本規格只處理「Case Import 明確指向一筆 provisional registration」的路徑。未帶 provisional
registration 的既有 Case Import 仍維持原有新建 Client／Order 行為；LINE 重送、行政人工取代
暫存登記、LINE 通知內容、合約簽署與任何 Finance／Payroll／Scheduling mutation 均不在本包範圍。

### 2. Command、Preview 與 root identity

`CaseImportIntent` 在需要消費暫存登記時，必須帶入 `provisional_registration_id`；該欄位是行政
從 Preview 顯示的 submitted registration 明確選擇的 immutable identity，禁止用姓名、電話、地址
或模糊搜尋自動配對。此路徑另要求 client attribute `line_id` 存在，且其 canonical value 必須等於
registration 的 `line_user_id`。未帶 `provisional_registration_id` 的 command 不讀取或改動任何
provisional registration。

Preview 唯讀載入下列 facts，並將它們納入 candidate／preview fingerprint：

1. registration id、`submitted` state、payload fingerprint、`line_user_id`；
2. registration 的 `client_id` 與 `beclass_record_id`，兩者都必須存在；
3. 被指向 client 的 LINE identity，以及 BeClass record 尚未關聯正式 `query_no` 的狀態；
4. 原有 Case Import 的 case existence、rate policy 與 bootstrap facts。

Preview 不得寫 event、receipt、mapping、notification 或任何 client／BeClass 欄位。Apply 收到的
`expected_import_version`、preview fingerprint 和 idempotency key 照既有 Case Import 契約驗證；
provisional facts 任一改變都回 `case_import_candidate_stale`，不得以新的資料靜默覆寫 Preview。

### 3. Apply 狀態機、鎖定與單一交易

狀態轉換只有：

```text
ProvisionalRegistration: submitted --Case Import Apply--> case_issued
```

同一 outer `CaseImportUnitOfWork` 的固定操作順序如下。所有 repository 方法接受 caller-owned
transaction；不得 hidden commit。

```text
claim idempotency key
→ lock case_no uniqueness facts
→ lock provisional registration by id
→ lock its provisional client and BeClass record
→ lock Case Import rate-policy/bootstrap facts
→ rebuild candidate and validate Preview fingerprint
→ update the existing provisional client with approved Case Import root attributes and case_no
→ create the Order and architecture bootstrap roots for that same client_id
→ bind the existing BeClass record to the issued query_no/case mapping
→ append case_import event and immutable provisional case_issued event
→ set registration status=case_issued and active_line_user_id=NULL
→ persist one Case Import receipt containing registration_id and case-issued event id
→ one commit
```

`active_line_user_id` 只能與 status transition 一起清空；不得先清空再嘗試建案。若 registration
已是 `case_issued`、case_no 已存在、provisional client／BeClass identity 與 Preview 不符、BeClass
已被其他 case 關聯，或任一 persistence step 失敗，整個 Unit of Work rollback，留下的狀態必須仍是
完整的 `submitted` 或完整的既有成功 receipt，絕不留下半套 Client、Order、Bootstrap、問卷關聯或
case-issued event。

### 4. Typed outcome、replay 與錯誤

成功 `CaseImportReceipt` 增加 optional `provisional_registration_id` 與
`provisional_case_issue_event_id`。同 key 且完全相同 command fingerprint 回原 receipt，不重建
Order、不重寫 client、不重複 append event；同 key 不同 payload 固定回 `idempotency_mismatch`。

新增或明確映射下列 typed blockers：

| Code | 類別 | 意義 |
|---|---|---|
| `provisional_registration_not_found` | domain blocked | 指定 registration 不存在。 |
| `provisional_registration_not_submitted` | conflict | registration 已核發或不在可消費狀態。 |
| `provisional_registration_identity_mismatch` | conflict | `line_id`、provisional client 或 BeClass identity 不一致。 |
| `provisional_registration_beclass_already_linked` | conflict | 問卷已關聯其他正式案件。 |
| `case_import_candidate_stale` | conflict | Preview 後 case、registration 或 bootstrap facts 已變。 |
| `case_import_duplicate` | conflict | `case_no` 已被正式案件使用。 |
| `transaction_failed` | unavailable/internal | storage、deadlock 或 timeout 造成整體 rollback；僅 retryable storage error 可重試。 |

不同 payload 的 LINE registration conflict 不是 Case Import 自動解決事項。存在 open
`provisional_registration_conflicts` 時，Apply 回 `provisional_registration_identity_mismatch`，由行政
先完成明確的人工作業；不得挑選任一 payload 自行併案。

### 5. Additive persistence contract

既有 `provisional_client_registrations` 保持 root table；不得刪除或改寫原送件 payload fingerprint。
新增一個 append-only `provisional_registration_case_issue_events`，至少保存
`registration_id`、`case_no`、`client_id`、`beclass_record_id`、`case_import_event_id`、
`idempotency_key`、command fingerprint、actor、correlation id、created_at，並以 registration id、
case_no 與 idempotency key 建立適當唯一約束，保證一筆 registration 不會被核發為兩案。

`case_import_receipts` 以 additive nullable columns 或等價 versioned result snapshot 保存
`provisional_registration_id` 和 `provisional_case_issue_event_id`，使同 key replay 可以完整回傳
receipt。schema 必須依 `db/schema_parts/` → `db/schema.sql` → versioned validation release metadata
更新；只可在 disposable／validation MySQL 驗證，不得套用正式資料庫。

### 6. 實作落點與 non-goals

| 層級 | 必要變更 |
|---|---|
| Domain | 擴充 Case Import intent／facts／candidate，使 provisional identity 與 fingerprint 為 typed root facts；定義 submitted→case_issued guards。 |
| Subsystem | 在既有 `CaseImportWorkflow` Preview／Apply 編排 provisional consumption；維持唯一 outer UoW 與 existing replay contract。 |
| Infrastructure | Case Import repository 實作 lock、existing-client merge、BeClass binding、event／receipt persistence；provisional repository 僅提供 typed locked facts／transition port，不另開 transaction。 |
| API／UI | 沿用正式 Case Import Preview／Apply，僅暴露已核對的 registration selection 與 typed errors；不新增 LINE direct writer。 |
| Validation | 以隔離 MySQL schema 驗證 FK、unique、row lock、rollback 與 receipt replay。 |

不得把 provisional registration 做成新的 Orders owner、不得以 UI payload 取代 fresh locked facts、不得
在 transaction 內發送 LINE，亦不得把這個 residual 併入 WP 56 的 Contract Signing write set。

### 7. 必要驗收與 completion evidence

| 層級 | 必要情境 |
|---|---|
| Module | submitted／case_issued guard、command fingerprint 與 optional receipt serialization deterministic。 |
| Subsystem | Preview 零寫入；指定 registration 正常 consume；same-key replay；same-key different payload；stale registration；open LINE conflict；duplicate case；每個 persistence point failure rollback。 |
| Domain | disposable MySQL 證明既有 client id 被升格、不新增 duplicate client、既有 BeClass 正確關聯、唯一 Order／Bootstrap roots 與 `case_issued` event 同次 commit。 |
| Concurrency | 兩個不同 idempotency key 競爭同一 registration 時只有一個成功；另一個得到 typed conflict，無 deadlock 或 partial write。 |
| Evidence | 更新本文件狀態、`02` 索引與 `03_追蹤清單與證據/` 的 receipt，記錄 source revision／digest、schema release identity、測試命令與結果。 |

完成判定是上述 acceptance 全數具備 current source 的 focused receipt，且 `49` 的 residual 不再存在；
只有那時才能將本文件標示為 `completed`。本規格本身不授權 production deployment、production schema
apply 或對 LINE 發送新的外部通知。

## 完成證據

2026-08-11 已完成 focused unit/workflow 與 disposable MySQL acceptance。證據固定於
`../03_追蹤清單與證據/evidence/2026-08-11_case_import_provisional_registration_closeout_receipt.md`：
驗證 submitted→case_issued、既有 Client 升格、BeClass 關聯、same-key replay、injected-failure
rollback 與兩個不同 idempotency key 的並發競爭。production deployment、production schema apply
與新的 LINE 外部通知仍未授權。
