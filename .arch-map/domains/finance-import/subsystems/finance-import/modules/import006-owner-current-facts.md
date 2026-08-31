# Module: import006-owner-current-facts

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
`IMPORT-006`已退出 runtime Anomalies。本 module只保留 Finance Import normal ingestion／classification／
reprocess與必要 owner validation／migration evidence，不再提供 anomaly current fact或corrected-source recovery lineage。

## Implementation
- `subsystems/finance_import/ingestion.py`
- `infrastructure/mysql/finance_import_owning_domain_composite.py`
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
