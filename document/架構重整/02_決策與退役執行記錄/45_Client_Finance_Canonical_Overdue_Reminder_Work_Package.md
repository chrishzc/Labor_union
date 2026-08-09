---
doc_type: work-package
authorized_by: user
authorization_date: 2026-08-08
---

# Client Finance Canonical Overdue Reminder Work Package

## Architecture

| Layer | Responsibility |
|---|---|
| Global | 銀行對帳單匯入是唯一付款結果事實；提醒不產生付款指令。 |
| Client Finance Domain | `client_obligations` 的未清償金額、到期日及 `open/settled` 是應收／客戶補助退還的 current projection。 |
| Anomalies Subsystem | 以每日 stable candidate universe 投影 `RECEIVABLE-001` 與 `RETURN-001`；不符合條件時由 current-state reducer 自動結案。 |
| MySQL module | 只讀上述 projection 與既有 alert source identity，讓已結清或已刪除的 candidate 仍可送出 inactive 狀態。 |

## State and boundaries

- `receivable_from_client` 的 `deposit`、`first`、`second`、`adjustment`：`open`、餘額大於零、且到期日早於掃描日才提醒人工核對銀行對帳單。
- `payable_to_client` 的 `refund`、`adjustment` 與 `subsidy_return`：同一條件下提醒人工核對應付資料、銀行對帳單與匯入結果；補助退還涵蓋可能由工會先行墊付的案件，但不建立付款命令。
- 銀行資料尚未匯入只代表未收到結果，不建立 `failed`、`bank_pending` 或自動 settlement。
- 掃描與 anomaly projection 共用既有單一交易；重跑以既有 fingerprint/idempotent reducer 收斂，不改寫 Client Finance ledger。

## Acceptance

- 同一案件多筆逾期義務只產生一個對應業務線的提醒，snapshot 列出每筆未清餘額。
- canonical obligation 結清、餘額為零、尚未到期或移除後，下次掃描送出 inactive 並自動結案。
- 掃描模組不再讀取 `client_payments` 的到期、應收、已收或補助退還欄位。
