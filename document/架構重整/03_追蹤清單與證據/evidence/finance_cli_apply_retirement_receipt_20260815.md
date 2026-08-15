---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Finance Import / Global Entry Governance
scope: Finance CLI apply retirement
---

# Finance CLI Apply 退役驗收收據

## 結果

`scripts/imports/import_finance_excel.py` 現在僅保留 workbook format preview／去敏 diagnostic。無論是否
提供 `--confirm-database`，`--apply` 都在 normalization、DB connection 與 typed ingestion 之前固定
失敗為 `finance_import_cli_apply_retired`；日常寫入只能走 authenticated Finance Web API。

| 驗收項目 | 結果 |
|---|---|
| Apply fail-closed | PASS：測試確認 `--apply` 零 ingestion、零 DB connection。 |
| Preview | PASS：preview 不呼叫 typed ingestion。 |
| Entry governance | PASS：queue 保留 operator-only diagnostic，明確指向 Finance Web replacement。 |
| Focused regression | PASS：Finance CLI、queue 與 import isolation 14 passed。 |
| DB／external effect | NOT_APPLICABLE：未連線、未寫入 DB、未呼叫外部 provider。 |

Restore trigger：Finance Web ingestion 事故或需要新的受控維運寫入時，另立 owner Work Package；不得恢復
CLI `--apply`。
