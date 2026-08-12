---
scope: 14_Government_Subsidy_Domain
status: verified-local-contract-and-disposable-mysql
verified_at: 2026-08-09
---

# Government Subsidy Domain 重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/14_Government_Subsidy_Domain.md`
- durable command：`../../04_已完成與上線封存/work_packages/40_Durable_Job_Government_Subsidy_Work_Package.md`
- Global readiness：`../../04_已完成與上線封存/superseded_specs/46_Six_Remaining_Gaps_Completion_Architecture.md`
- historical selection/release boundary：`../../04_已完成與上線封存/work_packages/51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md`

## 已驗證架構邊界

- Claim planning／submission／approval、government receipt／reversal、M:N allocation、
  aggregate projection、receipt/outbox 都由 Government Subsidy owner 寫入 append-only facts。
- Finance Import composite 只建立 typed `ReceiptIntent`，以 borrowed Unit of Work 呼叫
  `GovernmentSubsidyLedgerWorkflow.apply_receipt_borrowed()`；inner workflow/repository 不 commit。
- 無唯一 batch 或 allocation 會回 typed review，而不以金額相同自動過帳；後續 funding
  recovery 經 Government outbox 交由 Client Finance／Staff Payables 追加 recovery link，
  不建立第二筆 payout 或混用客戶 ledger。
- API Apply 透過 durable job envelope；worker 以 command identity／lease/retry 保證 at-least-once
  delivery 不重複正式交易。
- 已移除無 production caller 的 legacy `receipt_reconciliation.py` direct writer；新鮮 v3
  inventory 為 669 findings／658 unique identities，disposition coverage 完整且沒有自動授權移除。

## 驗收

```text
Government Subsidy + subsidy advance focused suite
39 passed, 5 skipped in 1.58s

tests/test_government_subsidy_durable_mysql_e2e.py
5 passed in 43.60s
```

E2E 使用暫時 `mysql:8.4` container，僅綁定 `127.0.0.1:33308`，資料庫為
`lu_test_government_subsidy_14`；container 已以 `--rm` 移除，未讀寫 `.env`、`union_db`
或 target host。pytest 未留下指定的 temporary base directory。

## 外部界線

政府公文外部保存與真實銀行對帳單格式品質仍需各自的 operator-approved external
acceptance；target-host worker supervision/TLS/latency 已依決策 53 退出產品 release gate。
本收據不將 fixture 或 disposable E2E 宣稱為 production deployment evidence。

## Current-source focused verification

```text
Government Subsidy, subsidy advance and retired direct-writer boundary suite
33 passed, 5 skipped in 1.52s
```

5 項 skip 都要求明確設定 disposable MySQL；本次沒有使用 `.env`、`union_db` 或 target host。
