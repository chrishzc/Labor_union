# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
呈現外部簽約完成回報、歷史簽回修復、最終 PDF 納管，以及客戶／服務人員 exact-target 完整契約自動套值。Preview 只回傳 typed values；React 不擁有簽約、文件或帳務根事實。

外部簽約案件 Query 在簽約 facts 尚未備齊時回傳零寫入 `preparing` 文件投影；預覽與未簽 PDF 準備不依賴已接受方案、簽約 session 或正式排班。交接／最終簽回命令沿用原 Domain 條件。
完整契約投影另提供候選資訊限定的 current-order-payment 查詢：未執行指派時使用 Orders current confirmed／預計日期投影 Finance，不要求舊方案仍有效或借用舊 commitment 服務量；一般完整契約查詢保留原方案／commitment 驗證。

外部平台交接不以 LINE 綁定為門禁：完整 current 未簽 PDF 備妥後，已綁定者建立提醒，未綁定者以 typed 人工通知對象保存於交接 receipt，Query／replay 保留送交當時結果。真正的身分錯配與版本衝突仍拒絕；無歷史簽回證據的新案件不顯示人工修復區。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`
- client: `ui_react/src/api/orders/contract_external_signing_client.ts`
- recovery state: `ui_react/src/adapters/orders/order_mutation_flow_store.ts` (per-case external-signing handoff and unsigned-PDF preparation unknown outcomes; received receipts permit owner readback only)
- `ui_react/src/api/orders/contract_full_preview_client.ts`
- `ui_react/src/components/OrderContractPreview.tsx`
- page: `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
- `api/routes/contract_external_signing.py`
- `api/dependencies/contract_external_signing.py`
- `api/schemas/full_contract_preview.py`
- `domains/contract_signing/external_signing.py`
- `infrastructure/db/contract_external_signing_repository.py`
- `infrastructure/db/contract_unsigned_pdf_repository.py`
- `infrastructure/db/external_staff_completion_port.py`
- `infrastructure/db/external_signing_handoff_notification_port.py`
- `infrastructure/file/browser_contract_renderer.py`
- `infrastructure/mysql/contract_context_repository.py`
- `infrastructure/mysql/contract_full_preview_repository.py`
- `infrastructure/mysql/contract_signing_document_query_repository.py`
- `subsystems/contract_signing/full_contract_preview.py`
- `subsystems/contract_signing/external_signing_workflow.py`
- `subsystems/contract_signing/final_document_workflow.py`
- `subsystems/contract_signing/line_delivery.py`
- `subsystems/contract_signing/unsigned_contract_pdf.py`
- `subsystems/orders/contract_completion_workflow.py`
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
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/`
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_actions.test.tsx`
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_client.test.ts`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_browser_contract_renderer.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_completion_workflow.py`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、recovery confirmation、unknown-outcome handling、final PDF readback、technical-detail disclosure or focused test location changes.

已備妥而未簽署的客戶 PDF 可經「重新產生客戶契約」沿既有 prepare 命令重讀 current facts；虛擬帳號改變會產生新來源 snapshot 及新 PDF。回讀後準備中／已交接畫面均保留新版 document ID，未知結果沿用原命令核對。客戶簽回草稿停用入口；client source writer 在原 UoW 鎖定案件、檢查 current plan 客戶簽署事件／外部回報與 contract identity，已簽署回 typed conflict，不覆寫歷史文件。
舊交接文件集合 hash 可由同案／方案的保存客戶版本證明，並維持 current staff set 相同；回讀新版客戶 PDF 不改舊 session hash，月嫂文件變更仍拒絕。
