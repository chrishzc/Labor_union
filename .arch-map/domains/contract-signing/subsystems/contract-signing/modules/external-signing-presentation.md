# Module: external-signing-presentation

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
簽約文件缺少 Client Finance／Payroll 初始資料時，只顯示實際缺漏原因及帶同案識別的客戶名冊連結；由既有名冊頁補齊，不在簽約頁嵌入帳務與排班操作面板，也不由契約 Query 自動建立其他 owner roots。
呈現外部平台交接、最終 PDF 納管，以及客戶／服務人員 exact-target 完整契約自動套值。管理端不顯示或背景查詢歷史簽回人工修復；歷史 API／receipt 保留。Preview 只回傳 typed values；React 不擁有簽約、文件或帳務根事實。

外部簽約案件 Query 在簽約 facts 尚未備齊時回傳零寫入 `preparing` 文件投影；預覽與未簽 PDF 準備不依賴已接受方案、簽約 session 或正式排班。交接／最終簽回命令沿用原 Domain 條件。
完整契約投影另提供候選資訊限定的 current-order-payment 查詢：未執行指派時使用 Orders current confirmed／預計日期投影 Finance，不要求舊方案仍有效或借用舊 commitment 服務量；一般完整契約查詢保留原方案／commitment 驗證。

外部平台交接不以 LINE 綁定或完整 current 未簽 PDF 備妥為門禁，只保存交接，不建立提醒。已有 current session（含已完成）可再次記錄，只 append receipt，不改簽署狀態或 status version；初次交接在 current session facts 可用時啟用；只有 PDF 尚未生成時，通過既有已接受方案、檔期及日期檢查後保存真實方案的案件層級 receipt（null session、版本 0），不虛構文件或簽約 facts。preparing Query 提前投影相同 blockers 與 `handoff_logged`。簽署提醒由人員在 LINE 官方帳號聊天後台手動選用範本。工會系統移除提醒寫入與案件畫面狀態，歷史提醒回執仍可唯讀查閱，舊提醒與舊契約下載通知由 LINE worker 在呼叫 provider 前取消，投遞歷史保留。
工作區同案推薦變更後，已掛載的契約下載及欄位預覽依 owner revision 重讀 current targets；舊服務段落不沿用至新推薦。既有檔案、進行中命令及結果未明的原操作保留，待可安全重讀時才更新，不因 revision 清除 recovery flow。

管理端提供瀏覽器列印、選用送交紀錄與獨立已簽 PDF 歸檔。歸檔查詢只依現行案件與可列出的月嫂分段取得欄位及已歸檔檔名。已確認的 PDF 由 Controlled Files 保存，與 Orders 完約事實及歸檔回執同交易提交；無未簽版本、送交、session、排班或帳務前置。舊 final-document API 保留歷史相容。

未簽契約由瀏覽器列印或另存 PDF。工作台不提供重產或直接下載按鈕，完約區塊顯示已簽檔名。已授權歷史讀取及版本保存契約沿用原入口。最後簽約遭拒顯示具體原因，已選文件保留。
舊交接文件集合 hash 可由同案／方案的保存客戶版本證明，並維持 current staff set 相同；回讀新版客戶 PDF 不改舊 session hash，月嫂文件變更仍拒絕。

本機測試可透過後端 `testing_skip_allowed` 能力與 `final-document/testing-skip` 產生各 current target 的 TEST ONLY 占位文件，經原 Preview 與明確測試確認完成後續流程；production／未知環境、遠端 DB 及 deployment profile 拒絕此能力。Apply 區分真實簽署確認與測試確認，fresh-lock 後拒絕文件模式不符，原 receipt 重播綁定確認模式。測試 reason／檔名與完成回讀保留「未驗證真實簽署」識別，不呼叫外部簽署／LINE provider。
若 Orders 已完成而目前 session 尚未回收文件，完整 TEST ONLY 集合的 Preview／Apply 借用 Orders typed Query（Apply 使用鎖定讀取）與 current plan 既有 commitment，沿用原契約 identity 完成測試文件納管及 session，不重複執行 Orders completion、Finance writer 或 commitment writer。原完整文件 Preview token 綁定既有 identity、Orders version、commitment 及文件集合；一般簽署文件不走此分支。
新案件正常建立契約並完成；已有 identity 而未完成者，TEST ONLY 流程沿用原 identity 執行正式 completion，Preview 與 Apply 均以同一 candidate identity 為準。這三種測試完成路徑依 owner facts 判定，不依案件編號。
簽約 Query 回傳 current `signing_blockers`，工作區在送交前顯示檔期／日期衝突與既有換人、改日期入口；瀏覽器列印維持可用。送交及新 completion 在原 UoW fresh-read；`MySqlExternalStaffCompletionPort` 借用 Scheduling canonical occupancy 與 segmented availability 核對跨案正式占用、有效 lock、不可服務期間，排除同案占用及 buffer。已完成 session／既有完成結果的測試文件回收不重簽；最後檔期鎖與排班 gate 保留。

## Implementation
- primary: `ui_react/src/components/ContractExternalSigningActions.tsx`
- client: `ui_react/src/api/orders/contract_external_signing_client.ts`
- recovery state: `ui_react/src/adapters/orders/order_mutation_flow_store.ts` (per-case handoff and unsigned-PDF preparation identities survive unknown outcomes/remount; receipts preserve the original result)
- `ui_react/src/api/orders/contract_full_preview_client.ts`
- `ui_react/src/components/OrderContractPreview.tsx`
- page: `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
- `api/routes/contract_external_signing.py`
- `api/routes/contract_signing.py`
- `ui_react/src/api/orders/contract_signing_mutation_client.ts`
- `ui_react/src/components/ContractSigningActions.tsx`
- `api/dependencies/contract_external_signing.py`
- `api/schemas/full_contract_preview.py`
- `domains/contract_signing/external_signing.py`
- `domains/orders/contract_completion.py` — 歸檔完成的 Orders 投影
- `infrastructure/db/contract_external_signing_repository.py`
- `infrastructure/db/contract_unsigned_pdf_repository.py`
- `infrastructure/db/external_staff_completion_port.py`
- `infrastructure/file/browser_contract_renderer.py`
- `infrastructure/mysql/contract_context_repository.py`
- `infrastructure/mysql/contract_full_preview_repository.py`
- `infrastructure/mysql/contract_signing_document_query_repository.py`
- `subsystems/contract_signing/full_contract_preview.py`
- `subsystems/contract_signing/external_signing_workflow.py`
- `subsystems/contract_signing/final_document_workflow.py`
- `subsystems/contract_signing/unsigned_contract_pdf.py`
- `subsystems/orders/contract_completion_workflow.py`
- `infrastructure/mysql/order_contract_completion_repository.py`
- `subsystems/contract_signing/client_contract_application.py`
- `subsystems/contract_signing/contract_renderer.py`
- `subsystems/contract_signing/template_catalog.py`
- `subsystems/contract_integration/contract_context.py`
- `db/templates/contracts/contract_client_copy.json`
- `db/templates/contracts/contract_staff_service.json`

## Contracts
- 直接歸檔後的一般首排由 Orders `service-date-confirmation` 借用 `subsystems/contract_signing/final_document_workflow.py` 的 `ArchivedCommitmentPort`，由 `infrastructure/db/external_staff_completion_port.py` 投影並建立缺少的精確人日承諾。沿同一 adapter 原 commitment writer，不補造簽回 session、事件或訂金；歸檔入口本身仍不要求服務承諾。
- 瀏覽器列印與案件層級交接後的同次回收銜接見正式規格 21 §3.2／§3.3；工作台沿用既有產製、交接及回讀入口。
- 管理端文件清單、核對摘要與回收以 current target 的 canonical Staff id 借用公會編號及姓名；選擇月嫂的選單按編號自然排序，保留 segment identity。已保存 PDF 與歷史寄送 payload 保留原內容。
- `.arch-map/requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- `.arch-map/requirements/12_Global_效能與UX體感架構.md`

### 契約欄位投影與瀏覽器列印 ^signing-current-projection-print

[需求書 §3.2](../../../../../requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#contract-current-projection-print) 定義列印範圍與欄位口徑。此投影使用目前來源，不要求先進入簽約、付款或正式排班。

| 負責角色 | 正式約定與接線 | 去哪查 |
| --- | --- | --- |
| Client Finance、Orders／資料來源 | 客戶契約讀客戶時薪、各期預計繳款日與本案虛擬帳號。預計日不讀實際入帳日，不借月嫂費率。 | `infrastructure/mysql/contract_full_preview_repository.py` 的客戶投影 |
| Scheduling、Payroll／資料來源 | 月嫂契約依精確分段對應同案、同人員的來源，讀各自服務區段與應付；不挪用其他月嫂或整案合計。不唯一時不猜。 | 同一 repository 的 `load_staff_projection` 與月嫂分段解析 |
| Contract Signing／後端、前端 | `FullContractPreviewApplication` 選用核准模板、驗映射後套入 typed 欄位。缺值是提示，不同於列印技術阻擋。已登入的 A4 HTML 入口依請求重讀同一投影，不快取、不建立檔案版本或簽署狀態；送交的檔期阻擋屬 §3.3。 | `full_contract_preview.py`、`api/routes/contract_external_signing.py`、`contract_full_preview_client.ts` |

驗證定位：`test_full_contract_preview.py` 的 `test_client_contract_uses_planned_due_dates_and_per_case_virtual_account`、`test_real_templates_render_multi_staff_summary_and_personal_service_days`、`test_preview_reports_null_required_owner_fact_without_blocking` 對照客戶日期、多人隔離及缺值。A4 版面另見 `test_browser_contract_renderer.py::test_browser_print_contains_full_approved_wording_and_a4_layout_without_pdf_engine`。此定位不宣稱實際瀏覽器列印或獨立的「訂單資訊－1／2、每週服務時間」三個介面已驗收。

```yaml archmap-impact
- kind: implements_requirement
  source: signing-current-projection-print
  target: '.arch-map/requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#^contract-current-projection-print'
```

### 交接紀錄與直接歸檔分開驗收

- 規格 #21 §3.3 的「記錄已送交」只留下交接回執；不代表拿到已簽 PDF 或 Orders 完約。§3.4 的直接歸檔不要求交接回執或 session；操作人確認簽名及內容，系統檢查檔案、案件與當前目標，不以 PDF 格式驗證代替簽名查核。
- 前端用案件的 `GET /api/v1/orders/{case_no}/contract-external-signing/signed-archive` 取得當前 `staff_segments` 與既有 `files`（未歸檔為 `null`）。同一路徑的 POST 接收客戶 PDF `client`，每份月嫂 PDF `staff` 必須對應同位置的 `staff_segment_ids`；後端以 segment ID 重核當前目標，不以月嫂姓名或檔名配對。若沒有可列出的月嫂分段，只需客戶 PDF；若有分段卻缺一份，拒絕整批。
- Contract Signing 依 `subsystems/contract_signing/final_document_workflow.py` 交 Controlled File 納管，並在同一交易記錄 Orders 完約與歸檔回執。成功回執可讀各目標的檔名及檔案識別；同一請求重送回原結果，不再完約一次。歸檔失敗不能標完約；已有的完約事實不因重送而覆寫。排班、訂金與帳務仍由各自的規格判定。

## Verification
- 直接歸檔正反對照：沿用下列 `test_final_document_workflow.py` 的無 session／未簽檔正例、缺月嫂分段檔及受控儲存失敗反例；這些隔離案例不驗通知、正式檔案或待辦看板推進。
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/`
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_actions.test.tsx` — L546–550 的既有介面測試斷言：後端未提供本機測試能力時，不顯示測試跳過操作。此案例不驗證後端授權或正式環境拒絕。
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_client.test.ts`
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_signing_mutation_client.test.ts`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_browser_contract_renderer.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_external_signing_workflow.py`
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_completion_workflow.py`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/test_final_document_workflow.py`
- routing: `.arch-map/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md`

## Change triggers
Reconcile when external signing presentation、recovery confirmation、unknown-outcome handling、final PDF readback、technical-detail disclosure or focused test location changes.
