# Client Refund Return Anomaly Package

## 1. 目的與已確認根因

一般客戶退款的銀行退回，不得因為對帳單含有「退款退回」文字、同一客戶帳號，或尚未
出現預期的銀行列，就自動沖正既有 `refund` ledger entry。

一位客戶可能有多筆一般退款；銀行入款也不一定含原退款的唯一識別。因此，未能唯一連結
原退款不是「可依金額猜配」的情況，而是必須保留的業務異常。沒有銀行列也不是付款失敗
根事實。

本 package 補上正式的 `CLIENTREFUND-001` 異常根事實與 recovery contract，供既有
`client_refund_return` Finance Import correction 使用。它只處理一般 `refund`，不得讀寫
`subsidy_return`、`subsidy_advance` 或 `client_payments.subsidy_refund_*` legacy projection。

### 1.1 Finance Import 辨識限制（歷史匯入紀錄；非本次驗收）

既有歷史 Finance Import reprocess 紀錄記載 2,659 個 occurrences、2,655 個
canonical rows；其中只有 279 筆存入列具有合法 `99781699 + 年度三碼 + 流水三碼` 的
客戶虛擬帳號。其餘 2,058 筆存入列缺少或具有無效虛擬帳號，597 筆支出列也沒有可唯一
連結的服務人員付款目標。

這些數字不是退款退匯的固定分類規則，也不是現行候選規則的真實資料驗收；它們只說明舊有
虛擬帳號 classifier 的覆蓋不足。故本 package 採用由強至弱、可稽核的候選辨識：

- 先由完整合法虛擬帳號或唯一銀行 reference 反解 case；
- 若缺少強識別，classifier 必須從姓名、備註、對方帳號與金額產生可重播的 candidate
  evidence，而非直接丟棄該筆；交易時間保留為重匯／人工覆核證據。把時間納入自動 score
  的 owner-fact contract 待真實資料驗收時一併完成；
- 只有候選集合唯一、證據沒有衝突，且同一 bank row 沒有命中既有業務付款時，才可送出
  typed business intent；正式 ledger 仍由 owning Domain 的 Preview／Apply 驗證；
- 無候選、多候選、證據衝突，或不同時間的兩筆銀行列均命中同一義務時，必須保留為
  `review_required`／疑似重複匯款，不得靜默核銷第二筆；
- 退款退匯的 `refund_reversal` 除候選辨識外，仍必須在 Apply 時唯一連結原 `refund`
  ledger entry、驗證金額與 fresh facts。姓名、帳號、摘要或金額不能單獨沖正 ledger。

因此，無法形成唯一且無衝突候選的列才保留為 Finance Import review root fact；不得透過
historical reprocess 改寫 canonical bank facts 來補造 case 或 refund target。

## 2. 不可變根事實

人員已檢閱銀行退匯通知後，若無法安全套用既有退款退匯 Preview，系統可建立一筆
`client_refund_return_review_event`。它不是 failed Preview 的副作用，也不是 ledger entry；
它是獨立、可稽核的人工確認事實，至少包含：

- immutable Finance Import bank row identity；
- 原本欲連結的 `refund` ledger entry identity；
- 該 entry 的 `case_no`；
- 不可為空的 reason 與 evidence；
- actor、idempotency key、correlation id 與建立時刻。

事件建立前必須確認 bank row 是正數入款、尚未被正式 ledger 使用，且原 ledger entry
確實為尚未退匯／沖正的 `refund`。任一條件無法成立時，不建立 review event，也不得改動
bank row、obligation、ledger、account version 或 Orders。

## 3. `CLIENTREFUND-001` current-state anomaly

| 項目 | 契約 |
| --- | --- |
| definition code | `CLIENTREFUND-001` |
| source Domain | Finance Import（銀行根事實） |
| owning recovery Domain | Client Finance |
| severity | blocking |
| fingerprint | `finance_import_row_id` + `refund_ledger_entry_identity` |
| source identity | `client-refund-return-review:<event-id>` |
| active predicate | review event 存在，且尚未有同一 bank row、同一原退款 entry 的 `refund_reversal` ledger entry |
| immutable occurrence | review event 建立時記錄一次；不得以 Alert 的 claim／resolve 取代 root fact |
| recovery action | `PreviewCorrectAndPostFinanceImportRow`，使用 `client_refund_return`、同一 bank row、同一原退款 ledger identity、原始 evidence 與 fresh versions |

Anomalies 的 claim／resolve 只管理人工工作流，不得改變 active predicate。若人員只是把 alert
標記 resolved，但尚未存在正式 `refund_reversal`，下次 projector／rescan 必須重新開啟。

## 4. 正常完成與失敗處理

```text
銀行退匯入款
  ├─ 可唯一證明原 refund + 金額精確相等
  │    → Finance Import correction Preview/Apply
  │    → append refund_reversal
  │    → reopen exact refund obligation
  │    → 不建立 CLIENTREFUND-001
  └─ 無法唯一證明／金額不符／目標已沖正
       → 人工確認 review event（零 ledger 寫入）
       → Finance Import outbox
       → CLIENTREFUND-001 open
       → 修正後重新 Preview/Apply
       → 唯一合法 refund_reversal 出現後 projector auto-resolve
```

金額不符、已沖正 target、跨 case target 或缺少 evidence 均不得「自動打平」。它們保持
review active，直到以新的合法 Finance Import correction 形成正確的 immutable
`refund_reversal`；不允許修改或刪除原 `refund`。

## 5. Transaction／outbox 邊界

建立 review event 必須使用單一 Finance Import outer Unit of Work：

1. 鎖 bank row 與 target `refund` ledger entry；
2. 驗證 root-fact eligibility；
3. append review event 與 idempotency receipt；
4. append `refund_return_review_recorded` Finance Import outbox；
5. 單次 commit。

Anomaly projector 是 outbox consumer，不能在上述 transaction 內直接寫 Alert。投影失敗只讓
outbox retry；不得 rollback 已提交的 review event，也不得改變 Client Finance ledger。

完成 `client_refund_return` correction 時，既有 `manual_correction_completed` outbox 必須同時
re-evaluate matching review event；只有 row identity 與 original refund ledger identity 都一致的
`refund_reversal` 才能使 `CLIENTREFUND-001` inactive。

## 6. API／UI 邊界

- 建立 review event 是 authenticated typed command，要求 stable idempotency key；它不是
  Preview，也不接受 UI 計算的金額。
- Finance Import UI 在 `client_refund_return` Preview 被 blocker 拒絕時，保留 operator 已輸入的
  row identity、target ledger identity、reason/evidence，提供「建立退款退匯待辦」入口。
- UI 只顯示後端 Query 的 candidate、typed error、job／outbox status 與 anomaly state；不能
  以關鍵字、客戶姓名、帳號或金額自行選定 target。
- Case page 仍只讀 case-owned obligation／ledger projection；未綁定 case 的 bank row 只可在
  Finance Import workspace 操作。

## 7. 驗收矩陣

1. 一筆真實格式台新入款可唯一對應既有一般退款時，直接 append `refund_reversal`，不建立
   `CLIENTREFUND-001`。
2. 同客戶兩筆同額 refund，銀行退匯無法唯一對應時，建立一筆 review event／outbox／blocking
   anomaly，且 client ledger、obligation、Orders 均零寫入。
3. 同 key 同 payload 重送回原 review receipt；同 key 不同 payload 回 idempotency conflict。
4. projector 失敗後重試只建立一個 current alert 與一個 occurrence，不改已提交 review event。
5. 以同一 bank row 及同一 target 合法 Apply 後，append 一筆 `refund_reversal`、重開 exact
   obligation，並讓 `CLIENTREFUND-001` auto-resolve；不同 row 或 target 不得解除。
6. subsidy return／advance bank row 或 ledger target 一律被拒絕，不建立一般退款 review event。
7. 隔離 MySQL E2E 需記錄 input Excel、review receipt、outbox、anomaly、ledger/reopen、replay
   與 source hashes；不得使用 `union_db`。
