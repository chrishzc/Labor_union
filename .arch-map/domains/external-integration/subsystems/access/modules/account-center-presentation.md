# Module: account-center-presentation

## Parent
- domain: `external-integration`
- subsystem: `access`

## Responsibility
呈現管理帳號清冊、安全操作確認與稽核詳情。UI只收集對象與操作原因；權限、version及idempotency由既有Access client與owner驗證，不以按鈕可見性授權。

## Implementation
- primary: `ui_react/src/pages/AccountManagementPage.tsx`
- primary: `ui_react/src/pages/AccountManagementPage.css`
- client: `ui_react/src/api/access/account_center_client.ts`
- client: `ui_react/src/api/access/account_directory_client.ts`
- client: `ui_react/src/api/access/audit_query_client.ts`

## Contracts
- `document/架構重整/01_規格基線/25_Access_Control正式規格.md`
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md`

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/account_query_page.test.tsx`
- test_root: `ui_react/src/tests/account_management_no_fake_mutation.test.tsx`

## Provenance
Access歸屬由既有parent宣告；上述UI／client／既有測試路徑為source_observed。沿用現有React harness，不移動測試。

## Change triggers
帳號操作入口、確認表單、稽核詳情或直接測試路徑改變。
