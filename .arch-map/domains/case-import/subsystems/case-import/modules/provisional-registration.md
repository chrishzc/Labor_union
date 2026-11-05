# Module: provisional-registration

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
擁有 LINE provisional registration candidate 的共用欄位規格及申請保存／核准建檔；非空身分證值在進入 persistence 前正規化為 ASCII 大寫字母加九碼數字，空值維持 optional。外部 Apply 只保存申請，工會核准才建立 Client／BeClass；LINE binding coordination 沿用同一 outer transaction。

## Implementation
- `subsystems/case_import/registration_staging.py` — Redis 待審、核准／拒絕／到期與原正式 writer 協調。
- `infrastructure/redis/registration_staging_repository.py`、`registration_connection.py`、`registration_maintenance.py` — 獨立耐久暫存、ACL／原子狀態及 AOF generation 清除。
- `api/registration_intake.py`、`api/registration_contracts.py`、`api/registration_token_verification.py`、`infrastructure/line/registration_token_verifier.py` — 無 SQL 公開接收與固定 LINE 驗證 transport。
- `api/dependencies/registration_applications.py`、`scripts/registration_maintenance.py`、`docker-compose.registration.yml`、`deploy/registration/` — 內部核准 composition、每分鐘 recovery／expiry 與每小時 AOF maintenance；部署仍需環境驗收。
- primary:
  - `domains/case_import/non_citizen_registration.py` — 非市民 HCM＋BeClass 合併欄位與必填驗證；原補助規則保持。
  - `infrastructure/mysql/non_citizen_case_number_repository.py` — 核准 outer UoW 內的年度列鎖配號，無 hidden commit。
  - `subsystems/case_import/non_citizen_registration_application.py` — 合併欄位轉成既有 Case Import typed intent，重用付款／薪資／排班 bootstrap。
  - `db/schema_parts/237_non_citizen_case_sequences.sql`、`db/schema_parts/1059_non_citizen_case_sequences.sql` — byte-identical fresh／preserve 年度計數表。
  - `domains/case_import/provisional_registration.py`
  - `subsystems/case_import/provisional_registration_application.py`
  - `infrastructure/mysql/provisional_registration_repository.py`
  - `subsystems/case_import/provisional_registration_types.py`
  - `db/schema_parts/1052_nas_registration_approval.sql`
- entrypoints:
  - `api/routes/line_identity.py`
  - `api/routes/registration_applications.py`
  - `ui_react/src/api/registration_applications/client.ts`
  - `ui_react/src/components/RegistrationApplications.tsx`
  - `ui_react/src/components/RegistrationApplications.css` — 待核准清單、申請明細及核准狀態，沿用專案色彩與響應式版面。
  - `ui_react/src/pages/ClientRegistryPage.tsx`（待核准需求分頁，保留名冊／虛擬帳號匯入）
  - `line/line_bot.py`（舊SQL問卷入口固定410，不因legacy開關復活）

## Dependencies
- outbound: `case-import/pairing-current-facts` — 正式退款欄位正規化及遮蔽；保留新核准與匯入各入口必填。
- inbound: `external-integration/line/registration-presentation` — canonical LIFF Preview／Apply transport。
- outbound: MySQL `beclass_records.survey_details` — persists the enriched registration survey payload。

## Contracts
- `17_External_Integration_LINE_Access正式規格.md` §5.1.1：非市民申請 snapshot 保存合併欄位，核准結果提供正式案件編號與核准時間；case-issue event 沿既有唯一關聯讀回，未核准不配號。
- canonical API keeps its existing `[12]` and checksum validation in `api/schemas/line_identity.py`。
- shared candidate owner guarantees non-empty persisted ID shape `^[A-Z][0-9]{9}$` without adding a prefix blacklist or legacy checksum rule。
- `17_External_Integration_LINE_Access正式規格.md` NAS-LINE-01：immutable application snapshot／version、內部核准一次、既有 completed receipts 不重建；`subsystems/line/identity_application.py` 協調核准與綁定，寫入失敗回滾。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/provisional-registration/` — 專用真 Redis／ACL／AOF 與無 SQL intake 驗收；不共用現有 cache instance。
- integration_root: `tests/domains/case-import/subsystems/case-import/integration/test_registration_staged_approval_mysql.py` — 新核准最小 SQL parent、正式欄位及 receipt 同交易。
- layout_status: `custom_current`
- focused: `tests/subsystems/case_import/test_provisional_registration.py`
- test_root: `tests/subsystems/case_import/test_provisional_registration.py`
- test_root: `tests/test_provisional_line_registration.py`
- layout_basis: 既有兩個 Case Import provisional registration 回歸入口為本次核准流程的直接 consumer；保留既有 discovery 與檔案位置，不新增平坦 root 或搬動未授權成果。
- integration_root: `ui_react/src/tests/registration_applications.test.tsx`
- integration_root: `tests/domains/case-import/subsystems/case-import/integration/test_non_citizen_registration_mysql.py` — 年度配號的 fresh、並行、回滾及 dump／candidate preserve 真實 MySQL 驗證。
- LINE coordination 的跨 owner atomicity 驗證由 LINE Subsystem 的既有 integration routing 承接，不歸本 leaf。
- routing: current Case Import subsystem verification root declared by the parent index; the focused file is the bounded current test placement for this owner.

## Provenance
- owner and persistence flow — `source_observed` — current repository。
- non-empty persisted ID format — `user_authorized` — current task acceptance。

## Change triggers
Reconcile when candidate field normalization、ID format、registration persistence owner、entrypoint or canonical test root changes。
