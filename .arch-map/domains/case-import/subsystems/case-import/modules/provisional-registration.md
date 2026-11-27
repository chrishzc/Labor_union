# Module: provisional-registration

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
擁有 LINE provisional registration candidate 的共用欄位規格（含 `特殊計費:胎數` 強制僅收 `單胞胎` 或 `雙胞胎`、非市民 `baby_info` 同步限值驗證與 `line_id` 選填保留 DB 欄位）及申請保存／核准建檔；非空身分證值在進入 persistence 前正規化為 ASCII 大寫字母加九碼數字，空值維持 optional。外部 Apply 只保存申請，工會核准才建立 Client／BeClass；LINE binding coordination 沿用同一 outer transaction。

## Implementation
- `subsystems/case_import/registration_staging.py` — Redis 待審、核准／拒絕／到期與原正式 writer 協調。
- `subsystems/case_import/passbook_image_validation.py` — 待審申請接收存摺封面時共用的圖片格式與內容驗證。
- `infrastructure/redis/registration_staging_repository.py`、`infrastructure/redis/registration_connection.py`、`infrastructure/redis/registration_maintenance.py` — 正式環境要求專用 Redis 與分角色憑證；明確的本機開發與測試可用共用 Redis。提供命名空間隔離、原子狀態及 AOF 維護。
- `api/registration_intake.py`、`api/registration_contracts.py`、`api/registration_token_verification.py`、`infrastructure/line/registration_token_verifier.py` — 無 SQL 公開接收與固定 LINE 驗證 transport。
- `api/schemas/line_identity.py` — 共用 `ProvisionalRegistrationPreviewRequest`／`ProvisionalRegistrationRequest` 的圖片識別與申請類型輸入契約。
- `api/dependencies/registration_applications.py`、`api/dependencies/registration_runtime.py`、`subsystems/case_import/registration_maintenance.py`、`scripts/registration_maintenance.py`、`docker-compose.yml`（`registration` profile）、`deploy/registration/` — 內部核准 composition、每分鐘 recovery／expiry 與每小時 AOF maintenance；部署仍需環境驗收。
- `deploy/registration/loopback_relay.py` — Windows 公開收件的本機轉送入口，以 `docker-compose.yml` 的 `registration-loopback` 綁主機 `127.0.0.1`；不掛憑證，透過 `registration-ingress` 轉送到 `registration-intake`，不執行申請審核或寫 MySQL。配置靜態檢查見 `test_registration_intake.py::test_public_container_has_no_mysql_settings_or_network_egress`；這不證明 Windows 實際啟動或 LINE 現場收件。
- primary:
  - `domains/case_import/non_citizen_registration.py` — 非市民 HCM＋BeClass 合併欄位與必填驗證；原補助規則保持。
  - `infrastructure/mysql/non_citizen_case_number_repository.py` — 唯讀預估配號，並在手動新案與 LINE 核准各自的 outer UoW 中共用年度列鎖與正式配號。
  - `subsystems/case_import/non_citizen_registration_application.py` — 重用 Case Import typed intent 與付款／薪資／排班 bootstrap，手動新案取得正式號碼。
  - `db/schema_parts/237_non_citizen_case_sequences.sql`、`db/schema_parts/1059_non_citizen_case_sequences.sql` — byte-identical fresh／preserve 年度計數表。
  - `domains/case_import/provisional_registration.py`
  - `subsystems/case_import/provisional_registration_application.py`
  - `infrastructure/mysql/provisional_registration_repository.py`
  - `subsystems/case_import/provisional_registration_types.py`
  - `db/schema_parts/1052_nas_registration_approval.sql`
- entrypoints:
  - `api/routes/line_identity.py`
  - `api/routes/registration_applications.py` — 支援非市民申請查詢／核准、手動建案、唯讀預估配號。
  - `ui_react/src/api/registration_applications/client.ts`
  - `ui_react/src/components/RegistrationApplications.tsx` — 非市民申請清單、明細核准、手動新案預估配號。
    - `sourceCaseNo` 使用既有 Client Registry typed Query 帶入來源案資料至手動新案表單，並以有界 `beclass_details` 保留目前報名聯絡補充與照護資料；表單姓名、地址、胎數等重新輸入值優先，不複製來源身分、LINE binding，送出仍走既有手動建案 API。
  - `ui_react/src/components/RegistrationApplications.css` — 申請清單、明細、手動建新案表單樣式。
  - `ui_react/src/pages/ClientRegistryPage.tsx`（非市民申請分頁，支援手動建新案與名冊／虛擬帳號匯入）
  - `ui_react/src/pages/ClientRosterPage.tsx` — 案件詳情提供資料帶入入口，透過 `#clients?tab=applications&source_case=...` 導向手動非市民新案。
  - `line/line_bot.py`（舊SQL問卷入口固定410，不因legacy開關復活）

## Dependencies
- inbound: `api/main.py`、`api/nas_apps.py` — 管理服務啟動每分鐘 expiry／recovery 與世代維護；公開 LINE 與 intake 不載入此生命週期。
- outbound: `case-import/pairing-current-facts` — 正式退款欄位正規化及遮蔽；保留新核准與匯入各入口必填。
- inbound: `external-integration/line/registration-presentation` — canonical LIFF Preview／Apply transport。
- outbound: Controlled File — `api/dependencies/registration_applications.py::_archive_client_passbook_cover` 將已收件圖片交給受控檔案服務並確認 finalize；收集資格與申請收尾仍由 Case Import 決定。
- outbound: MySQL `beclass_records.survey_details` — persists the enriched registration survey payload。

## Contracts
- `17B_Case_Import與非市民Redis待審正式規格.md` §3.1：非市民申請 snapshot 保存合併欄位，核准結果提供正式案件編號與核准時間；case-issue event 沿既有唯一關聯讀回，未核准不配號。
- canonical API keeps its existing `[12]` and checksum validation in `api/schemas/line_identity.py`。
- shared candidate owner guarantees non-empty persisted ID shape `^[A-Z][0-9]{9}$` without adding a prefix blacklist or legacy checksum rule。
- [Case Import §3.2](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#32-核准前問卷不得進-mysql-與獨立-redis-7-架構reg-boundaryreg-redisreg-expiry) 是正式建案、原申請回執與收尾條件的權威。`subsystems/line/identity_application.py` 同交易提交正式資料及原申請回執；提交後由 `subsystems/case_import/registration_staging.py` 依有圖／無圖條件完成歸檔或直接完成 Redis 收尾。歸檔失敗不等於 SQL 回滾；復原沿用原申請與操作，不另配案件編號。
- 管理端在核准中使用「查詢原申請處理結果」；唯讀 detail 可回 `status=approving`、`approved=false`、原 `case_no` 和 `approved_at_utc`，但不回問卷欄位。案號和時間只證明已有 SQL 回執，不能據此認定歸檔、Redis 收尾或 LINE 投遞已完成。

## Current implementation

- 候選版本 `9dd304bc70b1922058b9bb5d854ca37b3bec5365` 的 `api/schemas/line_identity.py` 以 `registration_kind` 區分圖片必填條件。`non_citizen` 可省略 `passbook_image_id`；`subsidy` 及未指定類型仍由 model validator 要求非空圖片識別。Domain builder 同步允許非市民無圖，且不將缺席圖片寫入 `_liff_meta`，銀行文字驗證保留。
- `api/registration_intake.py::preview`／`submit` 均以後端建立的 candidate 呼叫 `_require_passbook_staged`。僅無圖的 `non_citizen` 略過圖片查詢；只要實際提供圖片識別，仍驗證同一已驗證 LINE 主體的暫存圖。兩入口已對齊 [Case Import §3.1「送件欄位與原申請查詢」](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#送件欄位與原申請查詢)，共用上傳入口及已送件舊案流程保留。

## Handoff boundaries

| 交界與接線 | 權威及適用條件 | 可觀察的讀回 |
| --- | --- | --- |
| LINE 正式頁／工作室預覽 → request schema → intake Preview／Apply | [LINE presentation](../../../../external-integration/subsystems/line/modules/registration-presentation.md) 定位畫面；[Case Import §3.1](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#31-非市民進件與配號nc-entrync-formnc-approvalnc-numbernc-stat) 決定欄位與類型分流。 | Preview 可用不等於保存；Apply 的原申請編號及公開 status Query 只證明收件及目前申請狀態。 |
| 原申請 → 正式 writer 與 MySQL 回執 | Case Import §3.2；`api/routes/registration_applications.py` → `RegistrationReviewApplication` → `subsystems/line/identity_application.py::approve_staged_registration`。 | 管理端原申請 detail 依 `registration_id` 查回 `case_no`／`approved_at_utc`；收尾中仍為 `approving`。正式名冊依相同案號核對正式案件。 |
| SQL 已提交 → Controlled File → Redis 終態 | Case Import §3.2 分有圖／無圖；有圖才經 `_archive_client_passbook_cover` 及 [Controlled File §§3、5、8.2](../../../../../requirements/30_Controlled_File_Storage_NAS正式規格.md#3-file_purpose_registry-與排除範圍) 確認歸檔。 | 有圖可依正式 file identity 經受控 Query／Download 讀取；無圖沒有圖片回執可等。兩者都由原申請讀回 `approved` 證明適用收尾已完成，圖片本身或 SQL 回執單獨不能證明。 |

由核准／歸檔端反向走讀時，先以原申請與操作核對 SQL 回執，再依 Case Import §3.2 判斷是否有圖；Controlled File 不反推收集資格。回到 §3.1.2 可區分舊待審與已歸檔資料，最後由 LINE presentation 找到原畫面與正式送件入口。此處是原文導航，不表示 Archmap 索引工具已成功正查或反查。

## Verification
- 候選 `9dd304bc…` 的[專項 CI](https://github.com/chrishzc/Labor_union/actions/runs/45854012939/job/140027497325) 通過 41 個表單／API 案例及 1 個隔離 MySQL 案例。無圖非市民已覆蓋 Preview／Apply／原申請查詢，並以真實 MySQL writer、原操作回執、同案號重送及正式 Client Registry Query 驗證核准與建案讀回；市民圖片必填及銀行文字反例保留。真 Redis 跨儲存端到端、正式附件實體歸檔環境與真實 LINE provider 未在此專項執行。
- 已覆蓋情境（替身 port）：非市民舊待審已附圖，模擬 SQL 已提交而受控歸檔失敗。原申請仍為 `approving` 且可回讀原案號；復原沿同一操作及回執，歸檔 port 確認成功後才完成待審終態、清除問卷及原暫存圖，不重複建案。終態替身會清除 candidate，覆蓋 recover 必須使用原 snapshot 刪圖的行為。
- test_root: `tests/domains/case-import/subsystems/case-import/modules/provisional-registration/` — 專用真 Redis／ACL／AOF 與無 SQL intake 驗收；不共用現有 cache instance。
- integration_root: `tests/domains/case-import/subsystems/case-import/integration/test_registration_staged_approval_mysql.py` — 新核准最小 SQL parent、正式欄位及 receipt 同交易。
- layout_status: `custom_current`
- focused: `tests/subsystems/case_import/test_provisional_registration.py`
- focused: `tests/subsystems/case_import/test_manual_non_citizen_case.py`
- test_root: `tests/subsystems/case_import/test_provisional_registration.py`
- test_root: `tests/subsystems/case_import/test_manual_non_citizen_case.py`
- test_root: `tests/test_provisional_line_registration.py`
- layout_basis: 既有兩個 Case Import provisional registration 回歸入口為本次核准流程的直接 consumer；保留既有 discovery 與檔案位置，不新增平坦 root 或搬動未授權成果。
- integration_root: `ui_react/src/tests/registration_applications.test.tsx`
- integration_root: `tests/domains/case-import/subsystems/case-import/integration/test_non_citizen_registration_mysql.py` — 年度配號的 fresh、並行、回滾及 dump／candidate preserve 真實 MySQL 驗證。
- LINE coordination 的跨 owner atomicity 驗證由 LINE Subsystem 的既有 integration routing 承接，不歸本 leaf。
- routing: current Case Import subsystem verification root declared by the parent index; the focused file is the bounded current test placement for this owner.
- 靜態來源（`domains/case_import/provisional_registration.py` L187–210）：選填證號欄位交由共用正規化；正規化遇到 `ValueError` 時，轉成 `INVALID_ROOT_FACTS` 領域錯誤。此段僅說明欄位驗證，不代表已驗證 Apply、核准、持久化或 LINE 流程。

## Provenance
- owner and persistence flow — `source_observed` — current repository。
- non-empty persisted ID format — `user_authorized` — current task acceptance。

## Change triggers
Reconcile when candidate field normalization、ID format、registration persistence owner、entrypoint or canonical test root changes。
