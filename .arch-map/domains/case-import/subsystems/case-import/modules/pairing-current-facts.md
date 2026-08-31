# Module: pairing-current-facts

## Parent
- subsystem: `case-import`

## Responsibility
提供`BECLASS-001`的Case Import／Client owner follow-up facts；`IMPORT-003`已退出 runtime Anomalies。
只承認HCM case、Client BeClass source、review lineage、row receipt與`bound_case_no`，不以姓名／電話相似度配對，且不建立 anomaly recheck。

## Implementation
- `subsystems/case_import/pairing_current_facts.py`
- `infrastructure/mysql/case_pairing_anomaly_recheck_sink.py`
- `domains/case_import/beclass_import_review.py`
- `subsystems/case_import/beclass_import_review_workflow.py`
- `subsystems/case_import/beclass_import_outbox_consumer.py`
- `infrastructure/mysql/beclass_import_review_repository.py`
- `subsystems/case_import/client_beclass_workbook_import.py`
- `infrastructure/mysql/client_beclass_workbook_import_repository.py`
- `api/routes/client_beclass_import.py`

## Consumers
- Case Import／Client owner follow-up only；不再有 Anomalies runtime consumer。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/`
