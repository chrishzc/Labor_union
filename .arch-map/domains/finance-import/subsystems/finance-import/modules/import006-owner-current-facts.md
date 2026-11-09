# Module: import006-owner-current-facts

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
`IMPORT-006`已退出 runtime Anomalies。本 module只保留 Finance Import normal ingestion／classification／
reprocess與必要 owner validation／migration evidence，不再提供 anomaly current fact或corrected-source recovery lineage。

## Implementation
- `domains/finance_import/cancellation_code.py` — 銀行格式限定的完整帳號／虛擬帳號 projection。
- `domains/finance_import/transaction_classifier.py` — 正常匯入的純分類與唯一 ownership 候選；永豐客戶入款使用完整銷帳編號，不採姓名／帳號／金額猜測；U13 台新只有備註六碼時以 `taishin_memo_case_requires_manual_scheme` 保留人工確認，不預設客戶補助退款或自動核銷。既有月嫂姓名路徑維持；一般退款原因碼使用 outgoing/client_refund。
- `scripts/imports/finance_formats/taishin.py` — 解析台新格式，原始備註保留全形、空白及換行，辨識正規化不回寫來源。
- `domains/finance_import/transaction_fingerprint.py` — canonical identity，指紋命中只計入匯入收據的重複筆數。
- `domains/finance_import/planning.py` — 正常批次配對計畫及待核對原因快照。不同客戶銀行來源不因相同義務而判重；多筆各自全額命中同一期款時，改為合計超收人工核對，避免重複自動清償。
- `subsystems/finance_import/ingestion.py`
- `subsystems/finance_import/import_workflow.py` — 正常匯入批次 Preview／Apply，逐筆正式核銷拒絕原因隨既有 durable job 失敗結果保存，未進入核銷的永豐客戶款配對原因沿原 Apply 收據保存。
- `subsystems/finance_import/staging.py` — 新工作簿交易寫入 canonical row 前確認唯一案件，政府款沿原整期分流；借用 caller transaction，無自行 commit。
- `subsystems/finance_import/identity_maps.py` — 匯入分類使用的精確帳號候選唯讀投影。
- `subsystems/finance_import/reprocessing.py` — 舊批次重新分類唯讀／rollback-only 診斷，historical Apply 已退役。
- `infrastructure/mysql/finance_import_owning_domain_composite.py`
- 永豐月嫂薪資的重配對按實際步驟產生 `pending_reason` 並沿原批次收據保存；缺預計撥款日不作月份不符，無符合金額不作候選不唯一。唯一單筆／合併款先借用 Staff Payables Preview 重驗帳戶及資格，失敗維持待核對；已入帳來源不重開。其他明細類別的既有配對規則不變。
- 台新月嫂補助的重配對先重讀原始備註，借用同一 Staff Payables 姓名驗證；缺日期、無未清／同月款、金額不符及多個有效配對依實際步驟保存原因。唯一單筆／合併款同樣委派 owner Preview 後才可自動核銷，台新不要求帳號，六碼不作月嫂證據；其他用途的 resolver 不變。
- `api/routes/finance_import.py`

## Verification
- test_root: `tests/domains/finance-import/subsystems/finance-import/modules/import006-owner-current-facts/`
