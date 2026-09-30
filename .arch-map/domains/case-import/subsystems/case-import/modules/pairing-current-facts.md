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
- `api/schemas/client_beclass_import.py`
- `domains/case_import/cooking_requirement.py`
- `subsystems/case_import/hcm_beclass_reconciliation.py`
- `infrastructure/mysql/hcm_beclass_reconciliation_adapter.py`
- `domains/case_import/beclass_correction.py`
- `subsystems/case_import/beclass_correction_workflow.py`
- `infrastructure/mysql/beclass_correction_repository.py`
- `infrastructure/mysql/effective_case_service_rate.py`
- `infrastructure/mysql/beclass_financial_sync.py`
- `POST /api/v1/admin/registries/clients/{case_no}/beclass/{preview|apply}`

## Correction boundary
- HCM／Client BeClass 唯一配對後，未知下廚需求由 Orders-owned cooking correction command 在同一 caller UoW 補入；已有帳務或無逐日排班不阻擋此單欄補正，服務資料鎖、fresh version 與已知值異動規則仍由 Orders 擁有。
- Effective corrections resolve the unique `bound_case_no`; `query_no` remains immutable source provenance and original imported BeClass fields remain unchanged.
- Any order without a bound BeClass row may create one `record_origin='admin_manual'` container during Apply; Preview remains zero-write, and all entered values continue through the same versioned correction state／event owner.
- A pre-service effective birth-count correction coordinates existing Client Finance／formally assigned Payroll impact in the same outer UoW. Absent financial roots only retain effective correction for later bootstrap; unassigned cases do not require full Payroll facts. Partial roots and orphan history remain blocked. Once service has started, birth count is financially locked while non-financial BeClass fields remain independently correctable.

## Consumers
- Case Import／Client owner follow-up only；不再有 Anomalies runtime consumer。
- cross-owner evidence: `tests/domains/case-import/subsystems/case-import/integration/test_registry_correction_disposable_mysql.py` — independent registry edits, absent roots and repeated assigned corrections; Case Import subsystem owns this integration proof.

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/`
