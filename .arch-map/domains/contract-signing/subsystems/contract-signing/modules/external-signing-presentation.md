# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
呈現外部簽約完成回報、歷史簽回修復、最終 PDF 納管，以及客戶／服務人員 exact-target 完整契約自動套值。完整契約 Preview只回傳 typed cell values，既有 Excel browser mirror負責列印／另存 PDF；不得建立第二套 server-PDF bytes owner或讓操作員改欄位值。一般操作層只顯示簽約進度、證據完整性、影響檢查、阻擋與完成結果；status version、session、event、receipt、digest 與 fingerprint 等技術資料只保留在預設收合詳情。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`
- `infrastructure/file/libreoffice_contract_renderer.py`
- `infrastructure/mysql/contract_context_repository.py`
- `infrastructure/mysql/contract_full_preview_repository.py`
- `subsystems/contract_signing/full_contract_preview.py`
- `subsystems/contract_signing/client_contract_application.py`
- `subsystems/contract_signing/contract_renderer.py`
- `subsystems/contract_signing/template_catalog.py`
- `subsystems/contract_integration/contract_context.py`
- `ui/api_clients/full_contract_preview_api_client.py`
- `ui/pages/form_management/tab3_contract_management.py`
- `ui/pages/form_management/shared.py`

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — Contract Signing 證據、Preview／Apply、idempotency 與 readback 規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與 closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/contract_external_signing_actions.test.tsx`
- test_root: `ui_react/src/tests/contract_external_signing_client.test.ts`
- test_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py`
- test_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview_ui_client.py`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、legacy recovery confirmation、unknown-outcome reconciliation、final PDF readback、technical-detail disclosure or focused test location changes.
