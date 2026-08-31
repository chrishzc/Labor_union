# Module: pairing-current-facts

## Parent
- subsystem: `case-import`

## Responsibility
提供`BECLASS-001`與`IMPORT-003`的exact accepted-mapping current facts與bounded recheck request；只承認HCM case、Client BeClass source、review lineage、row receipt與`bound_case_no`，不以姓名／電話相似度配對。

## Implementation
- `subsystems/case_import/pairing_current_facts.py`
- `infrastructure/mysql/case_pairing_current_issue_adapter.py`
- `infrastructure/mysql/case_pairing_anomaly_recheck_sink.py`
- `subsystems/case_import/client_beclass_workbook_import.py`
- `infrastructure/mysql/client_beclass_workbook_import_repository.py`
- `api/routes/client_beclass_import.py`

## Consumers
- `subsystems/anomalies/case_pairing_current_issue_consumer.py`

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/`
