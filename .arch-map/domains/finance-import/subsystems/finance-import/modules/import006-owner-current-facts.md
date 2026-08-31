# Module: import006-owner-current-facts

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
提供IMPORT-006 authoritative current fact；canonical source正確時同batch rebuild，source錯誤時只承認accepted ingestion同UoW保存的exact successor lineage。

## Implementation
- `domains/finance_import/anomaly_remediation.py`
- `subsystems/finance_import/current_anomaly_facts.py`
- `subsystems/finance_import/ingestion.py`
- `infrastructure/mysql/finance_import_current_issue_adapter.py`
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
