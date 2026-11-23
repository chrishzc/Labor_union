# Module: pairing-current-facts

## Parent
- subsystem: `case-import`

## Responsibility
提供`BECLASS-001`的Case Import／Client owner follow-up facts；`IMPORT-003`已退出 runtime Anomalies。
只承認HCM case、Client BeClass source、review lineage、row receipt與`bound_case_no`，不以姓名／電話相似度配對，且不建立 anomaly recheck。

## Implementation
- `domains/case_import/client_beclass_validation.py` — Client BeClass 識別欄位與可補正欄位的匯入驗證。
- `domains/case_import/client_beclass_binding.py` — 客戶與案件的唯一配對分類及 BeClass 案件不可綁定原因型別。
- `domains/case_import/import_field_issues.py` — 去敏欄位問題型別及BeClass current owner逐欄重驗。
- `subsystems/case_import/current_import_field_issues.py` — HCM／成功BeClass共同問題Query，有界candidate分頁與逐案去重。
- `infrastructure/mysql/import_field_issues_repository.py` — created receipt root_id／review_identity與accepted bound_case_no關聯；失敗重匯不附掛舊案件。
- `api/dependencies/import_field_issues.py` — 共用Query組成，供名冊與通知工作台使用。
- `api/routes/import_field_issues.py` — 管理員唯讀 GET /api/v1/case-import/field-issues。
- `api/schemas/import_field_issues.py` — 共用問題與分頁HTTP型別。
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
- `api/schemas/client_beclass_import.py` — 同一問卷列可提交同一客戶的多個案號，人工綁定明細按案件回傳。
- `ui_react/src/api/case_import/client_beclass_workbook/client.ts` — immutable workbook Preview／Apply transport。
- `ui_react/src/api/case_import/client_beclass_workbook/schemas.ts` — 候選案件、確認配對及綁定結果契約。
- `ui_react/src/adapters/case_import/client_beclass_workbook_adapter.ts` — 預覽分類筆數守恆及候選資料投影。
- `ui_react/src/api/case_import/client_beclass_workbook/errors.ts` — typed 匯入失敗與結果待確認說明。
- `ui_react/src/components/ClientBeClassWorkbookPairing.tsx` — 客戶 BeClass 預覽的逐組配對抽屜、同客戶案件多選與整批確認。
- `domains/case_import/cooking_requirement.py`
- `subsystems/case_import/hcm_beclass_reconciliation.py`
- `infrastructure/mysql/hcm_beclass_reconciliation_adapter.py`
- `domains/case_import/beclass_correction.py`
- `domains/case_import/order_information.py` — Case Import-owned 原始照護欄位與有效 correction 的 named scalar projection，供名冊及訂單資訊使用。
- `domains/case_import/registration_details.py` — 身分證字號與三節假日雙薪意願的 bounded 問卷投影、證號格式正規化及非必要輸出去敏。
- `subsystems/case_import/beclass_correction_workflow.py`
- `infrastructure/mysql/beclass_correction_repository.py`
- `infrastructure/mysql/effective_case_service_rate.py`
- `infrastructure/mysql/beclass_financial_sync.py`
- `POST /api/v1/admin/registries/clients/{case_no}/beclass/{preview|apply}`

## Correction boundary
- `registration_details` 投影本案唯一綁定問卷的 `id_number`／`holiday_double_pay`，兩欄沿用 BeClass correction state／version／event／receipt。
- HCM／Client BeClass 唯一配對後，未知下廚需求由 Orders-owned cooking correction command 在同一 caller UoW 補入；已有帳務或無逐日排班不阻擋此單欄補正，服務資料鎖、fresh version 與已知值異動規則仍由 Orders 擁有。
- Effective corrections resolve the unique `bound_case_no`; `query_no` remains immutable source provenance and original imported BeClass fields remain unchanged.
- Workbook Apply stores one source copy per selected case within the workbook row transaction. The unique source key is `(query_no, bound_case_no)` and each case resolves its own correction record.
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
- 靜態來源（`subsystems/case_import/pairing_current_facts.py` L69–79）：owner 讀回不完整可與配對原因並列；零筆對應、多筆對應、唯一對應但映射不一致分別回傳不同的型別化原因。這段不驗證實際配對、匯入或資料庫。
