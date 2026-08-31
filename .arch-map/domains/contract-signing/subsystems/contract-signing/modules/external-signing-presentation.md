# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
呈現外部簽約完成回報、歷史簽回修復與最終 PDF 納管的既有 Query／Preview／Confirm／Apply／readback 流程。一般操作層只顯示簽約進度、證據完整性、影響檢查、阻擋與完成結果；status version、session、event、receipt、digest 與 fingerprint 等技術資料只保留在預設收合詳情。不得改變簽回證據血緣、idempotency、未知結果不得重送或 fresh readback 完成判定。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — Contract Signing 證據、Preview／Apply、idempotency 與 readback 規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與 closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/contract_external_signing_actions.test.tsx`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、legacy recovery confirmation、unknown-outcome reconciliation、final PDF readback、technical-detail disclosure or focused test location changes.
