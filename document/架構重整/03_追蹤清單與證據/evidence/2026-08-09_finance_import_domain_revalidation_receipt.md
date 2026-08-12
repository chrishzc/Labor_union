---
scope: 09_Finance_Import_Domain
status: verified-local-contract
verified_at: 2026-08-09
---

# Finance Import Domain 重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/09_Finance_Import_Domain.md`
- 決策／執行依據：
  - `../../04_已完成與上線封存/superseded_specs/27_Finance_Import_Historical_Reprocess_Completion_Decision_Package.md`
  - `../../04_已完成與上線封存/receipts/30_Finance_Import_Legacy_Import_Path_Repair_Receipt.md`
  - `44_Finance_Import_CLI_Test_Adapter_Work_Package.md`
  - `../../04_已完成與上線封存/work_packages/51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md`

## 本次實作與修復

- Historical Reprocess 的人工 owner selection 現為**選用**補充證據：有既有強證據且可唯一
  分類的 row 可不帶 selection；同一 batch 只可對實際歧義 row 提供 selection；批次外 row
  會以 typed validation error fail closed。
- manual owner candidate 的 fingerprint 已納入 locked `client_obligations.projection_version`。
  Preview 後 obligation 被其他合法交易變更時，fresh rebuild 會得到不同 fingerprint 並回
  `stale_preview`，不會以新 obligation version 靜默 Apply。
- Historical Reprocess 的 owning-domain posting context 已支援其 typed request；此前
  `bind_request()` 錯把它當 correction request，讀取不存在的 `selection` 而中止。
- `finance_import_reprocess_runs.actor` 現保存實際操作 actor，不再寫死
  `historical_reprocess`；人工 selection event 仍獨立保存 actor、case、obligation、evidence、
  batch／canonical／obligation versions、preview fingerprint 與 idempotency key。
- Streamlit 與 typed API 接受空 selection list，並清楚標示僅無法由強證據判定 owner 的 row
  才需要人工選案證據；Apply 仍使用 durable job、固定 idempotency key 與 job polling。
- Workbook ingestion 失敗會先 rollback 主交易，再以獨立連線追加 `FinanceImportAttempt`；該紀錄
  僅有 command／source SHA-256、phase、safe error code、時間與 outcome。相同 idempotency key
  重送直接回原 attempt，不會再次執行 workbook transaction；成功 attempt 則連結 completed batch。

## 隔離驗收

```text
Focused Finance Import / Historical Reprocess suite
155 passed, 1 skipped in 3.46s

Historical Reprocess contract suite (after actor audit repair)
34 passed in 1.75s

Disposable MySQL E2E
test_historical_owner_selection_posts_once_without_mutating_bank_root_fact
1 passed in 10.55s

Ingestion attempt ledger contract
6 passed in 1.15s
```

E2E 使用暫時的 `mysql:8.4` 容器，僅綁定 `127.0.0.1:33308`，資料庫為
`lu_test_finance_import_09`；測試後容器以 `--rm` 移除且專用 pytest 暫存目錄已清除。
它驗證真實格式台新 workbook 的 unresolved row 在人工 selection 後：canonical
`bank_references` 未改寫、selection event 完整追加、Client Finance refund ledger／allocation
成立、reprocess run 保存實際 actor，並且 exact replay 只回原 receipt。

## 分類品質證據界線

本收據不宣稱 fixture 或此一隔離 workbook 已量化真實銀行資料的分類正確率／誤配率。
已去識別的真實銀行格式 Excel 已作為 parser、normalization 與完整處理鏈路的產品驗收來源；
未來取得可合法重播的實際資料分布樣本後，再追加強／弱證據候選統計與分類品質 evidence。
這是持續品質改善，不是產品完成或 release gate。target-host worker recovery acceptance 已依
決策 53 退役。

## Current-source replay revalidation

同一 idempotency key 被不同 workbook command 重用時，ingestion receipt 與 independent
attempt ledger 都回傳可判讀的 `idempotency_conflict`；不會把內部衝突例外降級成空白
`ValueError`。這維持 CLI、API 與 direct workflow caller 相同的 safe-replay 契約。

```text
Finance Import source, classifier, identity-map and historical-reprocess suite
148 passed, 20 skipped in 3.51s
```

20 項 skip 均要求明確設定的 disposable MySQL；沒有連線到 production database。
