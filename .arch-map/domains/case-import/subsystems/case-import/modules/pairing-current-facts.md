# Module: pairing-current-facts

## Parent
- subsystem: `case-import`

## Responsibility
提供`BECLASS-001`的Case Import／Client owner follow-up facts；`IMPORT-003`已退出 runtime Anomalies。
只承認HCM case、Client BeClass source、review lineage、row receipt與`bound_case_no`，不以姓名／電話相似度配對，且不建立 anomaly recheck。

## Implementation
- `domains/case_import/refund_account.py` — 共用退款欄位正規化、typed有效來源及遮蔽。
- `infrastructure/mysql/beclass_refund_account.py` — 一般／補助退款快照委派的唯一有效帳戶Query，無寫入。
- `scripts/repair_registration_refund_accounts.py` — 預設唯讀採納預覽，唯一bound原問卷才可由原correction Q/P/A補正；真實Apply須另行授權，不重寫原問卷或既有金融快照。
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
- `ui_react/src/api/case_import/client_beclass_workbook/client.ts` — immutable workbook Preview／Apply transport。
- `ui_react/src/api/case_import/client_beclass_workbook/schemas.ts` — 候選案件、確認配對及綁定結果契約。
- `ui_react/src/adapters/case_import/client_beclass_workbook_adapter.ts` — 預覽分類筆數守恆及候選資料投影。
- `ui_react/src/api/case_import/client_beclass_workbook/errors.ts` — typed 匯入失敗與結果待確認說明。
- `ui_react/src/components/ClientBeClassWorkbookPairing.tsx` — 客戶 BeClass 預覽的逐組配對抽屜、左右連線與整批確認。
- `domains/case_import/cooking_requirement.py`
- `subsystems/case_import/hcm_beclass_reconciliation.py`
- `infrastructure/mysql/hcm_beclass_reconciliation_adapter.py`
- `domains/case_import/beclass_correction.py`
- `domains/case_import/order_information.py` — Case Import-owned 原始照護欄位與有效 correction 的 named scalar projection，供名冊及訂單資訊使用。
- `subsystems/case_import/beclass_correction_workflow.py`
- `infrastructure/mysql/beclass_correction_repository.py`
- `infrastructure/mysql/effective_case_service_rate.py`
- `infrastructure/mysql/beclass_financial_sync.py`
- `POST /api/v1/admin/registries/clients/{case_no}/beclass/{preview|apply}`

## Correction boundary
- HCM／Client BeClass 唯一配對後，未知下廚需求由 Orders-owned cooking correction command 在同一 caller UoW 補入；已有帳務或無逐日排班不阻擋此單欄補正，服務資料鎖、fresh version 與已知值異動規則仍由 Orders 擁有。
- Effective corrections resolve the unique `bound_case_no`; `query_no` remains immutable source provenance and original imported BeClass fields remain unchanged.
- Named care／bonus／floor-agreement fields share the existing BeClass correction state／version／event／receipt and effective projection. Corrected NULL clears an original value／field issue, unchanged bool／number scalars retain their type. Holiday bonus and floor-agreement text do not invoke financial sync; floor-fee amounts use Orders Terms and birth count retains its existing financial coordination.
- Any order without a bound BeClass row may create one `record_origin='admin_manual'` container during Apply; Preview remains zero-write, and all entered values continue through the same versioned correction state／event owner.
- A pre-service effective birth-count correction coordinates existing Client Finance／formally assigned Payroll impact in the same outer UoW. Absent financial roots only retain effective correction for later bootstrap; unassigned cases do not require full Payroll facts. Partial roots and orphan history remain blocked. Once service has started, birth count is financially locked while non-financial BeClass fields remain independently correctable.
- Effective refund account corrections (`refund_bank_code`, `refund_account_no`) automatically coordinate Client Finance `sync_refund_recipient_snapshots` in the same outer UoW, backfilling immutable snapshots for open client refund obligations and resolving pending recipient status (`recipient_ready=True`).

## Consumers
- Case Import／Client owner follow-up only；不再有 Anomalies runtime consumer。
- `ui_react/src/pages/DataImportPage.tsx` — 客戶 BeClass 工作簿預覽、確認匯入與綁定明細。
- cross-owner evidence: `tests/domains/case-import/subsystems/case-import/integration/test_registry_correction_disposable_mysql.py` — independent registry edits, absent roots and repeated assigned corrections; Case Import subsystem owns this integration proof.

## Verification
- layout_status: `custom_current`
- layout_basis: Backend owner-local tests use the canonical Python root; React transport tests mirror this Module under the existing frontend test layout.
- test_root: `tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/`
- test_root: `ui_react/src/tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/` — Client BeClass transport 與逾時結果確認。
