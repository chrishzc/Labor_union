# Module: finance-import-correction

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
組合 Finance Import correction 的 typed Query／Preview／Apply 與 durable outcome readback；正式帳務 mutation 仍委派給 owning Domain。
銀行人工核對提供原流水的客戶退款及部分退款入口，沿 Client Finance typed Query 選取待退款，並以既有 partial flag 委派 owner；核銷結果完成後讀回剩餘款並刷新清單。
正常補助退款候選在 Preview 先借用 Client Finance owner funding／eligibility 檢查；不符時保留 business pending，不宣稱 ready-dispatch，也不阻擋同批其他合法款項。

## Implementation
- primary:
  - `infrastructure/mysql/finance_import_repository.py`
  - `subsystems/finance_import/query.py` — manifest count and review list cover all unresolved canonical bank facts (manual review, business pending, blocked and unposted create), including unmatched cases; formal owner postings, reconciliation receipts and successful dispatches exclude processed rows.
  - `infrastructure/mysql/finance_import_owning_domain_composite.py` — 補助退款只委派 Client Finance owner；代墊判斷與人工核銷共用 owner funding facts，不在 importer 重算。
  - `ui_react/src/api/finance_import/finance_import_correction_client.ts`
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
