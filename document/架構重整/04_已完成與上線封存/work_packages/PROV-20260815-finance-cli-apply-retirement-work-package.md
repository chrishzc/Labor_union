---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Finance Import / Global Entry Governance
domain: Finance Import
subsystem: Legacy CLI apply retirement
implementation_authorization: granted-by-user-2026-08-15
---

# Finance Import CLI Apply 退役工作包

## Scope

`scripts/imports/import_finance_excel.py` 保留為 operator-only 的 workbook format preview／去敏報告工具，
但 `--apply` 在任何 DB connection 或 typed ingestion 前固定回傳
`finance_import_cli_apply_retired`。日常 Finance 寫入 replacement 是 authenticated
`POST /api/v1/finance-import/workbooks/ingest` 與其 Preview／Apply 流程。

不改 Finance API、schema、normalizer、reprocess diagnostic CLI 或任何 Case Import lane。

## Acceptance

1. CLI preview 零 DB 寫入；`--apply` 零 DB connection、固定 retired error。
2. queue 明確標記 CLI 為 read-only operator diagnostic，並指向 Web replacement。
3. Finance CLI、entrypoint queue focused tests 與 `git diff --check` 通過。

## 完成證據

2026-08-15 `--apply` 已在任何 workbook normalization、DB connection 或 typed ingestion 前固定
失敗；保留 preview diagnostic 與其 Web replacement。驗收收據：
`../03_追蹤清單與證據/evidence/finance_cli_apply_retirement_receipt_20260815.md`。
