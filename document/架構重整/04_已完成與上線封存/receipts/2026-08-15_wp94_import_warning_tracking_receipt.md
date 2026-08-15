---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Anomalies
---

# WP94 匯入警示查詢與人工追蹤驗收收據

## 範圍

完成 WP90/WP92 deferred 的欄位級 import warning typed Query、狀態 Preview／Apply、
receipt-first idempotency replay、MySQL event/receipt/outbox persistence 與異常中心去敏 UI。
未實作 WarningReferral、source reimport association、auto-resolve predicate、LINE delivery 或
任何 source/root correction。

## 驗收結果

| Gate | 狀態 | 證據 |
|---|---|---|
| Domain／Subsystem／API／UI client focused suite | PASS | `10 passed in 1.83s`；見下列 command。 |
| Disposable MySQL repository E2E | PASS | event、receipt、outbox、same-key replay 均在 `lu_test_wp94_import_warning_tracking` 驗證。 |
| HTTP → MySQL E2E | PASS | authenticated route Preview、Apply、Query 使用真實隔離 schema。 |
| Streamlit headless smoke | PASS | `streamlit_ui_smoke=PASS`，port `8514`，process 已停止。 |
| 外部通知／來源修正／WarningReferral | NOT_RUN | 明確 out-of-scope，沒有 side effect。 |

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_import_warning_tracking.py tests/test_import_warning_tracking_workflow.py tests/test_import_warning_tracking_api.py tests/test_import_warning_tracking_api_client.py tests/test_import_warning_tracking_disposable_mysql_e2e.py tests/test_import_warning_tracking_api_disposable_mysql_e2e.py --basetemp .pytest_tmp/wp94-final
```

結果：`10 passed in 1.83s`。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | WP94 只使用既有 WP92 part 195 tables。 |
| Change inventory | PASS | 無 schema-only、seed、backfill 或 destructive change。 |
| Static release／descriptor／plan | PASS | 使用 bootstrap 完整 assembly；release `labor-union-validation-schema-2026-08-15-v3` 包含 `195_import_warning_tracking.sql`。 |
| Engine verification | PASS | disposable schema `lu_test_wp94_import_warning_tracking` 的 repository 與 HTTP E2E 通過。 |
| Developer acceptance | NOT_RUN | WP94 不操作既有 developer-local database。 |

本包沒有 DB schema mutation；隔離 MySQL 驗收不授權對任何既有資料庫執行 mutation。
