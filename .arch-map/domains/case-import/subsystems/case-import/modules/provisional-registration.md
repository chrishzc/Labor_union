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
- outbound: MySQL `beclass_records.survey_details` — persists the enriched registration survey payload。

## Contracts
- `17B_Case_Import與非市民Redis待審正式規格.md` §3.1：非市民申請 snapshot 保存合併欄位，核准結果提供正式案件編號與核准時間；case-issue event 沿既有唯一關聯讀回，未核准不配號。
- canonical API keeps its existing `[12]` and checksum validation in `api/schemas/line_identity.py`。
- shared candidate owner guarantees non-empty persisted ID shape `^[A-Z][0-9]{9}$` without adding a prefix blacklist or legacy checksum rule。
- `17B_Case_Import與非市民Redis待審正式規格.md` §3.2：`subsystems/line/identity_application.py` 同交易提交正式資料及原申請回執；提交後由 `subsystems/case_import/registration_staging.py` 交 Controlled File 確認歸檔，再完成 Redis 終態和清理暫存。歸檔失敗不等於 SQL 回滾；復原沿用原申請與操作，不另配案件編號。
- 管理端在核准中使用「查詢原申請處理結果」；唯讀 detail 可回 `status=approving`、`approved=false`、原 `case_no` 和 `approved_at_utc`，但不回問卷欄位。案號和時間只證明已有 SQL 回執，不能據此認定歸檔、Redis 收尾或 LINE 投遞已完成。

## Verification
- 待驗情境：用附有合成存摺封面的非市民申請。令第一次核准在 SQL 提交後、受控歸檔時失敗；以管理端唯讀查原申請，再讓復原作業用同一操作完成。預期中斷時仍只有一筆正式案件，原案號可讀但未顯示核准完成；恢復後歸檔可讀、原問卷及暫存圖已清理，同案號進入已核准。再次查詢或重送同一核准不再建案。驗證不接正式 LINE。
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
