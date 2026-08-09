---
scope: 16_Staff_Payables與Client_Refund正式規格
status: proven-current-evidence
verified_at: 2026-08-09
---

# Staff Payables 與 Client Refund 正式規格重新驗證收據

## 裁決追溯

本輪以 `25`、`32`、`42`、`43`、`45` 與 `46` 的後續裁決核對第 16 份規格：退款、補助退還、
退款退匯與 receipt reversal 保持不同 immutable ledger event；銀行對帳單匯入是付款結果的
唯一根事實；逾期提醒只導向人工核對，不能推論 payment failure；Staff Payables 與 Client
Finance 只可由 Accounts Payable Export 的 read-only typed view 併列輸出，不得互相抵銷。

## 現行落地與驗收

- Client Refund 的 partial／full allocation、refund return／reversal、`CLIENTREFUND-001`、
  canonical overdue reminder、Finance Import borrowed UoW dispatch、Accounts Payable Export 和
  legacy-writer exit 都有正式 module、subsystem、adapter、API 與 thin UI 邊界。
- Staff Payout 的 payout／return／reversal、exact obligation link、replay、rollback、outbox 與
  archive bytes 契約均由 typed owner 實作。
- 本機聚焦驗證：54 passed、23 skipped。跳過項只要求顯式設定 disposable MySQL，並非
  production assertion failure。
- 只綁定 `127.0.0.1` 的 MySQL 8.4 disposable database 重新驗證：5 passed，包括 G06
  退款／沖正保持 Orders service-data lock、退款退匯 review/anomaly，以及 Staff Payout
  payout／return／reversal 的 durable replay／crash recovery。

固定、去識別化格式契約與隔離資料庫構成本機驗收；不得把它宣稱為真實銀行對帳單。target-host
部署驗收已依決策 53 退役；preserve-data hard rehearsal 仍是 Global external gate，並非本
Domain 功能缺口。
