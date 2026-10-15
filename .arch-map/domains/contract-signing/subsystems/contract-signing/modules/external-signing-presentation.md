# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
簽約文件缺少 Client Finance／Payroll 初始資料時，只顯示實際缺漏原因及帶同案識別的客戶名冊連結；由既有名冊頁補齊，不在簽約頁嵌入帳務與排班操作面板，也不由契約 Query 自動建立其他 owner roots。
呈現外部平台交接、獨立簽署提醒、最終 PDF 納管，以及客戶／服務人員 exact-target 完整契約自動套值。管理端不顯示或背景查詢歷史簽回人工修復；歷史 API／receipt 保留。Preview 只回傳 typed values；React 不擁有簽約、文件或帳務根事實。

外部簽約案件 Query 在簽約 facts 尚未備齊時回傳零寫入 `preparing` 文件投影；預覽與未簽 PDF 準備不依賴已接受方案、簽約 session 或正式排班。交接／最終簽回命令沿用原 Domain 條件。
完整契約投影另提供候選資訊限定的 current-order-payment 查詢：未執行指派時使用 Orders current confirmed／預計日期投影 Finance，不要求舊方案仍有效或借用舊 commitment 服務量；一般完整契約查詢保留原方案／commitment 驗證。

外部平台交接不以 LINE 綁定或完整 current 未簽 PDF 備妥為門禁，只保存交接，不建立提醒。已有 current session（含已完成）可再次記錄，只 append receipt，不改簽署狀態或 status version；初次交接仍由 current session facts 啟用。獨立提醒確認一次涵蓋客戶及所有 current 月嫂，fresh-lock 後以既有 committed delivery tasks 及 generic command receipt 同一 outer UoW 保存；未綁定對象保留當時的人工通知清單，身分錯配與版本衝突仍 typed 拒絕。提醒不推進簽約版本、不影響文件驗收；Query 回讀最後提醒，新交接標示未包含提醒，舊交接保留歷史通知事實。
工作區同案推薦變更後，已掛載的契約下載及欄位預覽依 owner revision 重讀 current targets；舊服務段落不沿用至新推薦。既有檔案、進行中命令及結果未明的原操作保留，待可安全重讀時才更新，不因 revision 清除 recovery flow。

管理端使用「下載契約 → 送交簽署 → 回收簽署文件」單一工作區；下載缺少的 current 未簽 PDF 時沿用正式生成命令，核對資料使用 exact-target 側邊抽屜。客戶與每段月嫂各自上傳、檢查及回讀簽回文件；未完整回收時只保存受控 staging，不推進簽約。最終 Preview 綁定完整文件集合，Apply 在既有 outer UoW 納管各文件並於既有 immutable receipt 保存 typed members，同時完成 Orders／Commitment／Client Finance 協作。已完成文件下載重新授權並限制為該案保存的 members；歷史單一最終 PDF 仍可讀取，不作新提交的替代。

客戶 PDF 可在已回報簽署或簽約完成後再次下載／重新產生，沿既有 prepare 命令重讀 current facts；虛擬帳號改變會產生新來源 snapshot 及新 PDF。回讀後準備中／已交接畫面均保留新版 document ID，未知結果沿用原命令核對。客戶簽回草稿停用重新產生入口；client source writer 在原 UoW 鎖定案件，只 append 新文件或重用相同 snapshot，不覆寫歷史簽回與業務完成事實。最後簽約遭拒顯示具體原因，文件檢查已通過的狀態保留。
舊交接文件集合 hash 可由同案／方案的保存客戶版本證明，並維持 current staff set 相同；回讀新版客戶 PDF 不改舊 session hash，月嫂文件變更仍拒絕。

本機測試可透過後端 `testing_skip_allowed` 能力與 `final-document/testing-skip` 產生各 current target 的 TEST ONLY 占位文件，經原 Preview 與明確測試確認完成後續流程；production／未知環境、遠端 DB 及 deployment profile 拒絕此能力。Apply 區分真實簽署確認與測試確認，fresh-lock 後拒絕文件模式不符，原 receipt 重播綁定確認模式。測試 reason／檔名與完成回讀保留「未驗證真實簽署」識別，不呼叫外部簽署／LINE provider。
若 Orders 已完成而目前 session 尚未回收文件，完整 TEST ONLY 集合的 Preview／Apply 借用 Orders typed Query（Apply 使用鎖定讀取）與 current plan 既有 commitment，沿用原契約 identity 完成測試文件納管及 session，不重複執行 Orders completion、Finance writer 或 commitment writer。原完整文件 Preview token 綁定既有 identity、Orders version、commitment 及文件集合；一般簽署文件不走此分支。
新案件正常建立契約並完成；已有 identity 而未完成者，TEST ONLY 流程沿用原 identity 執行正式 completion，Preview 與 Apply 均以同一 candidate identity 為準。這三種測試完成路徑依 owner facts 判定，不依案件編號。
簽約 Query 回傳 current `signing_blockers`，工作區在送交前顯示檔期／日期衝突與既有換人、改日期入口；下載維持可用。送交、提醒及新 completion 在原 UoW fresh-read；`MySqlExternalStaffCompletionPort` 借用 Scheduling canonical occupancy 與 segmented availability 核對跨案正式占用、有效 lock、不可服務期間，排除同案占用及 buffer。已完成 session／既有完成結果的測試文件回收不重簽；最後檔期鎖與排班 gate 保留。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`
- client: `ui_react/src/api/orders/contract_external_signing_client.ts`
- recovery state: `ui_react/src/adapters/orders/order_mutation_flow_store.ts` (per-case handoff、unsigned-PDF preparation and signing-reminder identities survive unknown outcomes/remount; receipts preserve the original result)
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
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_external_signing_workflow.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_completion_workflow.py`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、recovery confirmation、unknown-outcome handling、final PDF readback、technical-detail disclosure or focused test location changes.
