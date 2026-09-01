# Module: finance-import-correction

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
組合 Finance Import correction 的 typed Query／Preview／Apply 與 durable outcome readback；正式帳務 mutation 仍委派給 owning Domain。

## Implementation
- primary:
  - `infrastructure/mysql/finance_import_repository.py`
  - `ui_react/src/api/finance_import/finance_import_correction_client.ts`

## Dependencies
- outbound: `client-finance | staff-payables | government-subsidy` — correction candidate 依 classification 委派 owner command。
- outbound: `anomalies` — unresolved source evidence 僅供 projection/recheck，不改 owner root。

## Contracts
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md` — Finance Import correction ownership。
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` — correction and owner delegation boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/finance_import_correction_client.test.ts`

## Provenance
- Finance Import correction repository/client ownership — `source_observed` — current source and typed client contract。
- Owner delegation boundary — `architecture_declared` — current Finance Import specifications。

## Change triggers
Reconcile when correction candidate fields、owner delegation、durable outcome contract or focused test location changes。
