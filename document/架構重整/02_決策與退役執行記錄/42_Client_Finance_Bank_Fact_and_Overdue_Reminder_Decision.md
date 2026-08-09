---
doc_type: architecture-decision
decision_date: 2026-08-08
status: human-confirmed
---

# Client Finance 銀行根事實與逾期提醒裁決

## 1. 裁決

人工確認：本系統不直接接收銀行付款結果。人員手動匯入銀行對帳單後形成的
canonical bank fact，才是客戶應收或應付已實際發生的唯一根事實。

因此系統不得建立或推論 `submitted`、`payment_failed`、`bank_pending` 等付款結果
狀態。尚未有可核銷 bank fact，只表示尚未取得銀行結果，不能表示付款失敗。

## 2. 逾期提醒

對任何 remaining amount 大於零的應收或應付，當 business date 已過 due date 且沒有
有效 allocation 時，建立或維持 canonical overdue reminder。提醒表示「請人員核對
銀行對帳單是否已匯入、是否需人工配對或補正」；它不改寫 obligation、ledger、
allocation 或 Orders lifecycle。

有效 bank fact 經 owning Domain 的 Preview／Apply 完成精確核銷後，提醒必須由根事實
投影自動解除。金額、對象或 bank identity 無法唯一決定時，維持提醒或對應 anomaly，
不得猜測 allocation。

## 3. 工會墊付

`subsidy_advance_due` 是 read-only reminder，不是付款指令。它依未結清
`subsidy_return` obligation、due date、claim-item entitlement 與政府 allocation 根事實
提示人員核對；系統不產生銀行指令，也不因到期自動寫入 client ledger。

人員在銀行系統完成付款並匯入對帳單後，Finance Import 才以該 canonical outgoing bank
fact 委派 Client Finance。唯一且符合 eligibility 的事實可被記錄為 normal
`subsidy_return` 或 `subsidy_advance`；其後政府 allocation 只可建立 immutable recovery，
不得新增第二筆 payout。

## 4. 驗收資料

不要求歷史真實銀行對帳單作為 production proof。驗收以固定、去識別化的格式契約案例
與逐列預期結果驗證：應收／應付資料正確、bank fact ingestion 正確、核銷正確，以及
逾期提醒在未核銷時開啟、核銷後解除。不得把合成 fixture 宣稱為真實銀行資料。

## 5. 實作邊界

下一個 Client Finance work package 必須將既有 `RECEIVABLE-001` 與 `RETURN-001` 的
來源從 legacy `client_payments` projection 遷移為 canonical obligation／ledger read model，
並提供 bounded reminder queue 與人工核對入口。它不包含銀行 API、付款指令或付款失敗
狀態機。
