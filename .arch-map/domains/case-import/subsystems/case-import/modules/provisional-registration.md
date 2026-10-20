# Module: provisional-registration

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
擁有 LINE provisional registration candidate 的共用欄位規格及申請保存／核准建檔；非空身分證值在進入 persistence 前正規化為 ASCII 大寫字母加九碼數字，空值維持 optional。外部 Apply 只保存申請，工會核准才建立 Client／BeClass；LINE binding coordination 沿用同一 outer transaction。

## Implementation
- primary:
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
  - `ui_react/src/pages/ClientRegistryPage.tsx`（待核准需求分頁，保留名冊／虛擬帳號匯入）
  - `line/line_bot.py`（legacy rollback compatibility）

## Dependencies
- inbound: `external-integration/line/registration-presentation` — canonical LIFF Preview／Apply transport。
- outbound: MySQL `beclass_records.survey_details` — persists the enriched registration survey payload。

## Contracts
- canonical API keeps its existing `[12]` and checksum validation in `api/schemas/line_identity.py`。
- shared candidate owner guarantees non-empty persisted ID shape `^[A-Z][0-9]{9}$` without adding a prefix blacklist or legacy checksum rule。
- `17_External_Integration_LINE_Access正式規格.md` NAS-LINE-01：immutable application snapshot／version、內部核准一次、既有 completed receipts 不重建；`subsystems/line/identity_application.py` 協調核准與綁定，寫入失敗回滾。

## Verification
- layout_status: `custom_current`
- focused: `tests/subsystems/case_import/test_provisional_registration.py`
- test_root: `tests/subsystems/case_import/test_provisional_registration.py`
- test_root: `tests/test_provisional_line_registration.py`
- layout_basis: 既有兩個 Case Import provisional registration 回歸入口為本次核准流程的直接 consumer；保留既有 discovery 與檔案位置，不新增平坦 root 或搬動未授權成果。
- integration_root: `ui_react/src/tests/registration_applications.test.tsx`
- LINE coordination 的跨 owner atomicity 驗證由 LINE Subsystem 的既有 integration routing 承接，不歸本 leaf。
- routing: current Case Import subsystem verification root declared by the parent index; the focused file is the bounded current test placement for this owner.

## Provenance
- owner and persistence flow — `source_observed` — current repository。
- non-empty persisted ID format — `user_authorized` — current task acceptance。

## Change triggers
Reconcile when candidate field normalization、ID format、registration persistence owner、entrypoint or canonical test root changes。
