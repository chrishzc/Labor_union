# Module: import006-owner-current-facts

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
`IMPORT-006`已退出 runtime Anomalies。本 module只保留 Finance Import normal ingestion／classification／
reprocess與必要 owner validation／migration evidence，不再提供 anomaly current fact或corrected-source recovery lineage。

## Implementation
- `domains/finance_import/cancellation_code.py` — 銀行格式限定的完整帳號／虛擬帳號 projection。
- `domains/finance_import/transaction_classifier.py` — 正常匯入的純分類與唯一 ownership 候選。
- `domains/finance_import/transaction_fingerprint.py` — canonical identity，指紋命中只計入匯入收據的重複筆數。
- `domains/finance_import/planning.py` — 正常批次配對計畫及待核對原因快照。
- `subsystems/finance_import/ingestion.py`
- `subsystems/finance_import/import_workflow.py` — 正常匯入批次 Preview／Apply，逐筆正式核銷拒絕原因隨既有 durable job 失敗結果保存，未進入核銷的永豐客戶款配對原因沿原 Apply 收據保存。
- `subsystems/finance_import/staging.py` — 新 canonical row、首次 occurrence 與初始分類，借用 caller transaction，無自行 commit。
- `subsystems/finance_import/identity_maps.py` — 匯入分類使用的精確帳號候選唯讀投影。
- `subsystems/finance_import/reprocessing.py` — 舊批次重新分類唯讀／rollback-only 診斷，historical Apply 已退役。
- `infrastructure/mysql/finance_import_owning_domain_composite.py`
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
