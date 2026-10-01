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
- `domains/finance_import/transaction_fingerprint.py` — canonical identity 與非指紋銀行事實差異比較。
- `subsystems/finance_import/ingestion.py`
- `infrastructure/mysql/finance_import_owning_domain_composite.py`
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
