# Module: import006-owner-current-facts

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
`IMPORT-006`已退出 runtime Anomalies。本 module只保留 Finance Import normal ingestion／classification／
reprocess與必要 owner validation／migration evidence，不再提供 anomaly current fact或corrected-source recovery lineage。

## Implementation
- `domains/finance_import/cancellation_code.py` — 銀行格式限定的完整帳號／虛擬帳號 projection。
- `domains/finance_import/transaction_classifier.py` — 正常匯入的純分類與對象候選；永豐客戶入款使用完整銷帳編號。台新原始備註先辨識月嫂姓名，客戶候選可由客戶姓名或六碼加返還用途辨識。同名候選先保存，預檢以六碼或唯一合格退款月份定位。僅六碼不足以確認新方案。一般退款原因碼使用 outgoing/client_refund。
- `scripts/imports/finance_formats/taishin.py` — 解析台新格式，原始備註保留全形、空白及換行，辨識正規化不回寫來源。
- `domains/finance_import/transaction_fingerprint.py` — canonical identity，指紋命中只計入匯入收據的重複筆數。
- `domains/finance_import/planning.py` — 正常批次配對計畫及待核對原因快照。不同客戶銀行來源不因相同義務而判重；多筆各自全額命中同一期款時，改為合計超收人工核對，避免重複自動清償。
- `subsystems/finance_import/ingestion.py`
- `domains/finance_import/ingestion.py` — 將來源分類與對象證據投影成初始正式分類事件，月嫂退匯保留月嫂身分供人工核對。
- `subsystems/finance_import/import_workflow.py` — 正常匯入批次 Preview／Apply，逐筆正式核銷拒絕原因隨既有 durable job 失敗結果保存，未進入核銷的永豐客戶款配對原因沿原 Apply 收據保存。
- `subsystems/finance_import/staging.py` — 新工作簿交易寫入 canonical row 前確認案件證據。台新無六碼且備註唯一辨識月嫂的出款，以及命中多位同名客戶的補助出款，先保留待核對；補助資格與日期由原預檢判定。政府款沿原整期分流；借用 caller transaction，無自行 commit。
- `subsystems/finance_import/identity_maps.py` — 匯入分類使用的精確帳號與姓名候選唯讀投影；台新客戶備註案件解析共用於銀行查詢、補助預檢及 Client Refund 正式驗證，僅姓名時須唯一對應客戶及案件。
- `subsystems/finance_import/reprocessing.py` — 舊批次重新分類唯讀／rollback-only 診斷，historical Apply 已退役。
- `infrastructure/mysql/finance_import_owning_domain_composite.py`
- subsidy preflight composition: `infrastructure/mysql/subsidy_confirmation_repository.py`（statement-workspace owner）— 僅原 Apply 生效，台新月嫂以原始備註確認身分，僅有姓名時以補助撥款月份查候選；多案保留原明細供人工選案，金額只驗證已定位款項。原 owner 驗證資金與核銷資格。原 outer UoW 一併確認方案、合法承接與核銷，不自行 commit。
- 永豐月嫂薪資的重配對按實際步驟產生 `pending_reason` 並沿原批次收據保存；缺預計撥款日不作月份不符，無符合金額不作候選不唯一。唯一單筆／合併款先借用 Staff Payables Preview 重驗帳戶及資格，失敗維持待核對；已入帳來源不重開。其他明細類別的既有配對規則不變。
- 台新月嫂補助的重配對先重讀原始備註，借用同一 Staff Payables 姓名驗證；缺日期、無未清／同月款、金額不符及多個有效配對依實際步驟保存原因。唯一單筆／合併款同樣委派 owner Preview 後才可自動核銷，台新不要求帳號，六碼不作月嫂證據；其他用途的 resolver 不變。
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
