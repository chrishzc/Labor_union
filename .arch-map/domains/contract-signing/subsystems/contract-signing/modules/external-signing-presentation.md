# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
呈現外部簽約完成回報、歷史簽回修復、最終 PDF 納管，以及客戶／服務人員 exact-target 完整契約自動套值。Preview 只回傳 typed values；React 不擁有簽約、文件或帳務根事實。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`
- client: `ui_react/src/api/orders/contract_external_signing_client.ts`
- page: `ui_react/src/pages/OrdersPage.tsx`
- `api/routes/contract_external_signing.py`
- `api/dependencies/contract_external_signing.py`
- `infrastructure/file/libreoffice_contract_renderer.py`
- `infrastructure/mysql/contract_context_repository.py`
- `infrastructure/mysql/contract_full_preview_repository.py`
- `subsystems/contract_signing/full_contract_preview.py`
- `subsystems/contract_signing/client_contract_application.py`
- `subsystems/contract_signing/contract_renderer.py`
- `subsystems/contract_signing/template_catalog.py`
- `subsystems/contract_integration/contract_context.py`
- `db/templates/contracts/contract_client_copy.json`
- `db/templates/contracts/contract_staff_service.json`

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md`

## Verification
- `ui_react/src/tests/contract_external_signing_actions.test.tsx`
- `ui_react/src/tests/contract_external_signing_client.test.ts`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、recovery confirmation、unknown-outcome handling、final PDF readback、technical-detail disclosure or focused test location changes.
