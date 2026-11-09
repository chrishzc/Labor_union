# Module: finance-import-correction

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
組合 Finance Import correction 的 typed Query／Preview／Apply 與 durable outcome readback；正式帳務 mutation 仍委派給 owning Domain。
銀行人工核對提供原流水的客戶退款及部分退款入口，沿 Client Finance typed Query 選取待退款，並以既有 partial flag 委派 owner；核銷結果完成後讀回剩餘款並刷新清單。
正常補助退款候選在 Preview 先借用 Client Finance owner funding／eligibility 檢查；不符時保留 business pending，不宣稱 ready-dispatch，也不阻擋同批其他合法款項。
退款／補助的人工更正 Preview 與 fresh Apply 均經同一 owner eligibility 預檢；Preview 只模擬本次明確選定的用途，不寫分類或銀行事實。正式入帳仍由原 owner fresh-lock。correction outcome 以可空的 `failure_code` 傳回已保存的 typed 原因，UI 預覽拒絕與背景失敗共用原因文案；舊操作沒有具體原因時明示缺漏。
客戶退款及客戶補助退款人工核對直接承接 Client Finance Preview 的核銷分配與手續費，typed `refund_summary` 呈現手續費及本次選取款項的核銷後餘額；銀行實付維持原流水金額。沿用 owner PreviewFingerprint 檢查預覽後異動，正式入帳前再比對，不另定手續費政策。
台新客戶補助退款亦可明選超退追償，沿既有flag與同一owner預覽／核銷；依原備註六碼確認案件、月嫂姓名優先且不要求帳號，來源日期及資金資格沿正式義務驗證。本類別原因對照不接受其他用途的姓名／帳戶或概括目標不明碼；配對成功清除舊pending reason。

## Implementation
- primary:
  - `domains/finance_import/correction.py` — 承接 owner 退款預覽結果，驗證所選款項與金額一致性。
  - `subsystems/finance_import/correction_workflow.py` — 人工退款／補助的唯讀 owner 預檢與 fresh Apply 重驗，其他款項沿原流程。
  - `infrastructure/mysql/finance_import_repository.py`
  - `subsystems/finance_import/query.py` — manifest count and review list cover all unresolved canonical bank facts (manual review, business pending, blocked and unposted create), including unmatched cases; formal owner postings, reconciliation receipts and successful dispatches exclude processed rows.
  - `infrastructure/mysql/finance_import_owning_domain_composite.py` — 補助退款只委派 Client Finance owner；代墊判斷與人工核銷共用 owner funding facts，不在 importer 重算。
  - `ui_react/src/api/finance_import/finance_import_correction_client.ts` — 退款／補助拒絕原因文案共用於銀行清單、Preview 及正式 Apply outcome。
  - `ui_react/src/components/FinanceImportCorrectionForm.tsx`
  - `ui_react/src/pages/FinancePage.tsx` — 銀行流水人工核对列的 exact-row 更正入口。

## Dependencies
- outbound: `client-finance | staff-payables | government-subsidy` — correction candidate 依 classification 委派 owner command。
- outbound: `anomalies` — unresolved source evidence 僅供 projection/recheck，不改 owner root。

## Contracts
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md` — Finance Import correction ownership。
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` — correction and owner delegation boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/finance_import_correction_client.test.ts`
- test_root: `ui_react/src/tests/finance_source_review_list.test.tsx`
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/finance-import-correction/`

## Provenance
- Finance Import correction repository/client ownership — `source_observed` — current source and typed client contract。
- Owner delegation boundary — `architecture_declared` — current Finance Import specifications。

## Change triggers
Reconcile when correction candidate fields、owner delegation、durable outcome contract or focused test location changes。
