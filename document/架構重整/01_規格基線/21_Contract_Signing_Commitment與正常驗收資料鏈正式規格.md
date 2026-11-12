# Contract Signing、月嫂與客戶簽約完成及正常驗收資料鏈正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Contract Signing Integration（`domains/contract_signing/`、`subsystems/contract_signing/`）
- 單一負責範圍：契約 Excel 模板上傳與欄位映射版本管理（`CTM-01～06`）、兩類契約現行欄位投影與瀏覽器 A4 列印、未簽 PDF 下載／重複產生、送交外部平台交接記錄與獨立簽署提醒（LINE ＋未綁定人工名單）、分開文件簽回與完整集合完約、本機測試手動跳過門禁（`testing_skip_allowed`）、`precontract_service_commitment` 守恆與 execution conversion，以及簽約前 Scheduling 檔期衝突檢核（`signing_blockers`）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Global Migration 與 Cutover Subsystem](10_Global_保留資料Migration與Cutover_Subsystem.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)。

## 2. 核心架構、SSOT 與狀態機

```text
完整案件／服務條件保存 → 自動計算訂金與各期客戶應付（可先核銷）
月嫂承接意願 → 客戶接受推薦方案 → 齊備確認服務日期後自動鎖定 waiting-deposit 檔期
→ 契約瀏覽器列印或下載未簽 PDF → 記錄已送交外部簽署平台 → 獨立發送 LINE 簽署提醒
→ 分別上傳回收全部月嫂與客戶已簽署 PDF（或本機受控 TEST-ONLY 跳過）
→ Apply 納管受控文件、建立 commitment 與 Orders contract_completed
→（訂金已核銷使訂單成立 AND contract_completed AND commitment_ready）
→ commitment exact conversion → execution assignment／schedule
```

### 2.1 分責與 SSOT

| Owner | Root facts／責任 | 不擁有 |
|---|---|---|
| Contract Signing | `template-catalog/` 核准版本、不可變 `contract_document_version`（opaque NAS reference + digest）、`contract_signing_event`、外部交接／提醒 receipt、檔案 access grant | Orders status、應收金額、execution schedule、LINE delivery 結果 |
| Scheduling Commitment | `precontract_service_commitment` 與服務日、`waiting-deposit` 自動鎖定與 exact conversion、正式排班／occupancy | 契約文件、應收、LINE |
| Client Finance | 訂金／第一二期應付／到期日與專屬虛擬帳號（`CLIENT_DEPOSIT_BANK_CODE` + 本案虛擬帳號） | 簽署證據、Orders status |
| Orders | `contract_completed` 事件、`contract_identity`、訂單生命週期 | 外部簽署檔案、assignment 日 |
| LINE Integration | 身分綁定、committed delivery task 與試送狀態 | 契約完成或 Orders 成立條件 |

- **嚴格分離原則**：訂金核銷（`訂單成立`）、簽約完成（`contract_completed`）、commitment 成立與 execution conversion 為四個正交事實；LINE 送達、檔案下載或瀏覽器列印均不構成簽署完成。
- **統一用詞**：介面與流程區分「**所有月嫂簽約完成**」與「**客戶簽約完成**」；`commitment` 為內部人員與精確服務日記錄，不得作為額外人工簽約關卡；應收一律於資料齊全時由系統自動同步（資料缺漏顯示「待確認」，不另設「建立付款義務」操作）。
- **雙方簽約完成作為通知前提**：客戶與所有月嫂皆完成簽約（Orders `contract_completed` 且 `contract_identity` 吻合現行契約）始可發送訂金繳費提醒與各期逾期待辦；未完成前不阻擋各期應付計算、到期日確定或合法銀行核銷。
- **非市民契約**：完全接受 [Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md) 之 `A＋民國年＋3碼流水號`、非市民自費政策與 5 天訂金／專屬虛擬帳號（禁止套用一般 9 碼公式或要求 HCM 來源）。

### 2.2 `waiting-deposit` 自動保留與代班例外

- **自動鎖定等待檔期**：客戶接受推薦方案（M3 `accepted` decision 不等於完成簽約或排班）與 Orders `confirmed_service_dates` 雙條件齊備時，後到條件的 Apply 在同一 outer UoW 借用 Scheduling writer 取得 `waiting-deposit` 檔期鎖（先鎖 staff occupancy mutex，再鎖 Orders／Matching；日期解析沿單月嫂原詢問區間與多月嫂明確分段，衝突回 typed error 全筆 rollback；不另設獨立「保留月嫂檔期」按鈕）。
- **服務中代班文件例外**：已有 assignment-owned 實際服務日後發生代班屬 Scheduling substitution lineage，不重開整案簽約；人員可選填 `substitution_supplement` 補充證據（archive 不可用亦不阻擋代班與薪資，文件本身不能改變金額或日期）。

## 3. 公開契約與流程

### 3.1 契約 Excel 模板與欄位映射版本管理（`CTM-01～06`）

- **`CTM-01`（受控上傳）**：`system_admin` 於「稽核與系統 → 契約模板管理」上傳 `.xlsx`、選工作表並檢視文字、欄寬、列高、字級、邊框、合併格及內嵌 PNG／JPEG（伺服器重驗；拒絕巨集、外部連結與圖表；非映射公式轉固定值）。
- **`CTM-02／03`（映射與零寫入示範預覽）**：映射僅可對應兩類契約既有 typed owner 欄位（合併格僅綁左上角）；預設可選擇「沿用目前版本映射」（超界／落在合併格內部須明確調整或捨棄後方可保存），缺少必填來源或重複位置即拒絕。示範套值 Preview 使用明示虛構資料（含銀行代碼設定），零寫入且不讀真實案件。
- **`CTM-04／05／06`（不可變版本存儲）**：原始 `.xlsx` bytes 與已驗證映射保存於契約 archive `template-catalog/`（以檔案鎖、`expected_catalog_version`、actor、idempotency key 原子更新目錄 head，不進入案件 DB 交易）；保存與啟用分離，啟用僅影響後續新產製版本，已產生／簽回文件維持讀取當次不可變模板摘要。

### 3.2 目前資料投影、缺值提醒與瀏覽器 A4 列印

- **免門禁預覽／列印**：訂單資訊－1、訂單資訊－2、每週服務時間、客戶契約與個人服務人員契約直接投影目前系統有效資料（HCM／BeClass 有效更正及目前方案）；預覽、下載或列印均**不以同意、accepted plan、簽約工作、付款、正式排班或開工為前提**。
  - **欄位狀態與休假公式**：缺值回傳 `missing | optional_empty | not_applicable` 提醒而不列技術 blocker；服務方式為「無休」或空白一律按「連續服務」推導預期日期、結束日與分期金額（已選休假星期與自訂休假維持有效；無法辨識非空值保留提醒）。多月嫂案個人契約僅列該人員各自區段與薪資（嚴禁跨人複製或顯示全案總額）。
  - **客戶契約關鍵欄位映射**：D29／B25 讀取 Client Finance 客戶時薪（不讀月嫂時薪）；C34／C35／C36 分別顯示訂金／第一期／第二期**預計繳款日**（C37 樓層費同訂金日；嚴禁寫入實際入帳日）；D36 固定顯示「`(CLIENT_DEPOSIT_BANK_CODE) 本案虛擬帳號`」（例如 `(807) 99781699...`）。
- **瀏覽器列印（零寫入）**：
  - Endpoints：`GET /api/v1/orders/{case_no}/contract-signing/client/print` 與 `GET /api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/print`（authenticated、不快取 HTML）。
  - 版面契約：A4 直向、8 mm 頁邊、194 mm 內容寬，等待字型載入後呈現完整條文與套值（維持合併格比例，避免列內斷頁）；列印不建檔案版本、receipt 或簽署狀態。
- **`preparing` 準備查詢**：`GET /api/v1/orders/{case_no}/contract-external-signing` 於尚無簽約工作時回傳 `HTTP 200`（`state=preparing`、`staff_segments` 與 `documents`），零虛構 session（案件不存在回 404）。

### 3.3 檔期衝突檢核、送交記錄與獨立提醒

- **簽約前檔期衝突檢核**：契約工作區 Query 即時投影 Scheduling canonical 占用、等待檔期鎖與不可服務期間，存在 hard conflict 時回傳 typed `signing_blockers`（提示「更換推薦月嫂／調整服務日期」並停用送交）；送交、提醒與完成命令在各自 UoW fresh-read 遭遇衝突固定回 `signing_staff_occupancy_conflict` 或 `signing_service_dates_unavailable`（零寫入；同案既有 waiting lock 不自相衝突，buffer 僅警示）。
- **不阻塞下載與重複送交**：
  - 客戶與每段月嫂未簽 PDF 缺失時由下載觸發生成（已簽署、有 `contract_identity` 或已完約亦允許再次下載；資料 snapshot 變動則 append 新版未簽 PDF 並保留原已簽檔案）。
  - 「記錄已送交簽署平台」不以所有系統 PDF 已生成為前置（支持瀏覽器列印工作流：無系統 PDF／session 時保存案件層級 receipt `session_id=null, version=0, matching_plan_id`），**不檢查 LINE 綁定亦不建立提醒**（允許重複記錄送交、append receipt 並保留目前狀態與版本；`handoff_included_reminders=false`）。
- **獨立簽署提醒（`POST .../contract-external-signing/reminders`）**：
  - 點擊「發送簽署提醒」直接執行（無額外確認視窗），依現行方案對象範圍鎖定 session／expected version（未交接、版本過期或身分錯配回 typed 拒絕），於獨立 outer UoW 建立已綁定對象之 committed LINE 文字訊息任務（含 `type: text` 與 `text`）與人工通知名單（未綁定對象不建虛構 job，介面明確標示「需人工通知」）；同鍵重播回原 receipt，提醒失敗或執行不影響契約文件與簽署版本。

### 3.4 分開文件回收、手工證明與本機測試跳過

- **分開回收與完整集合完約**：
  - 介面僅提供「契約文件 → 送交簽署與提醒 → 回收簽署文件」（移除「檢查簽署文件」按鈕與「歷史簽回人工修復」區塊）；各目標（1 份客戶契約 ＋ 所有 current 月嫂契約）分別上傳經 Controlled Files staging 保存。
  - 最終 Preview（opaque token 綁定完整檔案集合與各 owner version）→ 明確確認簽署 → Apply 於單一 outer UoW 納管全部受控 NAS PDF（DB 僅存 opaque object reference ＋ SHA-256，嚴禁暴露實體路徑／UNC／presigned URL，下載限 authenticated attachment 並寫 security audit）、完成 session、建立 `precontract_service_commitment`、寫入 `orders.contract_identity` 與 `contract_completed`，並核對沿用 Client Finance 已同步之訂金及各期義務（計價未變不遞增 Finance version、不覆寫既成 `訂單成立`）。錯誤訊息直接回傳繁中具體業務原因，不掩蓋版本／檔期／測試門禁原因，且不遺棄已選檔案。
- **手工證明（`manual_attested`）**：線下紙本／現場簽回時，管理員可透過獨立人工認證 Preview／Apply 上傳真實簽回證據並填寫 `confirmation_method` 與必填 `reason`，形成 `staff_signed_received`／`client_signed_received` 與完約（不宣稱 LINE 送達）。
- **本機受控測試跳過（`testing_skip_allowed`）**：僅於 `APP_ENV=development|dev|local|test`、loopback MySQL（`union_db`／`lu_test_*`）且無 deployment profile 時開放；呼叫 `final-document/testing-skip` 產生完整目標 `TEST-ONLY-` 占位 PDF（明示未驗真實簽署），並搭配互斥 `testing_skip_confirmed=true` 完成完約（若案件既有 `contract_identity` 或 `commitment` 則予以沿用不覆蓋）。

### 3.5 Execution Conversion、Idempotency 與 Typed Errors

- **Execution Conversion**：僅在 `訂單成立 AND contract_completed AND commitment_ready` 下執行。鎖定 commitment、Orders、Finance settlement、matching plan 與相關 staff occupancy，驗證同案方案、分配結果與總服務日數。月嫂回報及代班沿 [Scheduling SSTART](02_Assignments_Scheduling_Domain.md#service-start-and-substitution) 核對人員與人日。工會依 [多月嫂排班](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction) 以預覽及具原因的確認分配首份班表，記錄新分配並保留原 commitment days、已簽文件及原簽回人員。
- **Idempotency 與 Conflict**：同鍵同指紋重播回原 receipt；同鍵異指紋回 `contract_signature_idempotency_conflict`；stale 版本固定 typed 409 且前端保持同一 idempotency key 供重試／查詢。
- **Commands／Stable Errors**：`GenerateContractDocumentVersion`、`DownloadUnsignedContractPdf`、`UploadReturnedContractDocument`、`Preview/RecordManualStaffContractAttestation`、`Preview/RecordManualClientContractAttestation`、`Preview/ApplyFinalSignedContractUpload`、`ConvertCommitmentToExecution`（命令回執寫入既有 `contract_signing_command_receipts`，條款 C34／C37 到期基準沿 Client Finance `deposit_due_date` 讀取）。Errors：`contract_document_empty | too_large | type_not_allowed | digest_mismatch | archive_failed`、`contract_status_version_conflict`、`contract_document_version_stale`、`signing_staff_occupancy_conflict`、`signing_service_dates_unavailable`、`external_signing_session_facts_unavailable`、`manual_contract_evidence_missing | confirmation_method_invalid | reason_missing | preview_stale | customer_acceptance_required`、`commitment_service_days_invalid | not_effective`、`contract_signature_idempotency_conflict`、`assignment_occupancy_conflict`。
- **Writer Exit**：所有可控模板與未／已簽文件存取一律經 `TemplateCatalog`、`ContractRenderer`、`ImmutableDocumentArchive`（`services/` 或 API／UI 嚴禁直改 `orders.contract_identity`、commitment 或 Finance obligation）。

## 4. 驗收標準

1. **`CTM` 模板管理與列印**：`.xlsx` 合併格／樣式檢視、巨集拒絕、沿用／缺件攔截、示範套值零寫入、版本啟用不改既有檔案、A4 8mm 194mm 瀏覽器列印雙模板驗證與 `state=preparing` 查詢。
2. **主流程與分離邊界**：檔期衝突在送交與提醒前精確阻擋；瀏覽器列印後不預存系統 PDF 仍可記錄送交；送交與獨立 LINE 提醒完全解耦（含未綁定人員工名單、文字欄位 `type/text` 正確性、同鍵防重）；分開簽回／`manual_attested`／`testing_skip` 於單一 UoW 原子建立 commitment、Orders 完成與訂金核銷銜接（下載不暴露實體儲存路徑）。
3. **本機受控 DB 驗收**：依 [Global Migration §6.1](10_Global_保留資料Migration與Cutover_Subsystem.md#61-本機開發-db-受控驗收91) 於受控 `union_db`／`lu_test_*` 通過 Module、Subsystem、Domain（訂金→訂單成立＋簽約→conversion、代班不重簽）與 Browser E2E。
