---
doc_type: work-package
authorized_by: user
authorization_date: 2026-08-08
---

# Finance Import CLI Test Adapter Work Package

`scripts/imports/import_finance_excel.py` 定位為測試期銀行 Excel 匯入 adapter。

- 正常模式只呼叫 typed `subsystems.finance_import.ingestion`，以固定
  `finance-import-cli-test` actor 與檔案內容衍生的穩定 idempotency key 建立 bank facts、
  initial classification、receipt 與 outbox；
- `--dry-run` 只做格式偵測、normalization 與列數摘要，零資料庫寫入；
- CLI 不再 import 或呼叫 legacy `services.finance_import_application`；
- 它不代表正式人工操作入口，未來 Web 匯入完成後可退休。
