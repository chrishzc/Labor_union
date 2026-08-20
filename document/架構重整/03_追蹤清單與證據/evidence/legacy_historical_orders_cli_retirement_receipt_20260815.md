---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Orders / Global Entry Governance
scope: Legacy historical-orders CLI retirement
---

# Legacy Historical Orders CLI 退役驗收收據

## 結果

已移除 `scripts/import_historical_orders.py`。它原本的 CLI 已固定拒絕執行，檔內卻仍有不可由日常
入口呼叫的 direct SQL 歷史 writer；現行 typed Web API 與受控的 `adopt_historical_orders.py` 維運入口
維持不變。

| 驗收項目 | 結果 |
|---|---|
| Source／queue | PASS：retired source 不存在，current entrypoint queue 不再列出該 CLI。 |
| Replacement | PASS：Web Preview／Apply 與受控 typed CLI 保留。 |
| Focused regression | PASS：entrypoint tests 11 passed；Historical Orders focused suite 25 passed、7 skipped。 |
| DB／external effect | NOT_APPLICABLE：本工作包沒有連線、寫入或變更 schema。 |

Restore trigger：Historical Orders intake 事故或需要重查 legacy parser 行為時，從 Git／封存歷史追溯；
不得還原 direct SQL writer，應使用 typed replacement。
