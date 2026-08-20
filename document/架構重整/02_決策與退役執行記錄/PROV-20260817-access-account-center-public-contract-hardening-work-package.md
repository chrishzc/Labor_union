---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-access-account-center-public-contract-hardening
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Access Control
domain: Access
approval_required: 核准此 exact Access Account Center Public Contract Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS
---

# Access Account Center public contract／React接線工作包

## Business boundary

只有sole enabled root可管理帳號；這不建立業務功能的role差異。帳號identity為`admin_user_id +
access_control_version`，不是React mock email/IP。MFA enrollment是使用者password-proof self-service；root只能
執行核准的reset，永遠不能看他人seed/QR/recovery codes。Audit是獨立masked read surface，Jobs另有owner。

## Exact production write set

- `subsystems/access/authentication_session.py`
- `api/schemas/account_center.py`
- `api/routes/account_center.py`
- `ui_react/src/api/access/account_center_schemas.ts`（new）
- `ui_react/src/api/access/account_center_client.ts`（new）
- `ui_react/src/pages/AccountManagementPage.tsx`
- `ui_react/src/pages/AccountManagementPage.css`

## Exact test／doc/validation write set

- `tests/test_access_account_center_public_contract.py`（new）
- `tests/test_access_account_center_disposable_mysql_e2e.py`（new）
- `ui_react/src/tests/account_management_public_contract.test.tsx`（new）
- `validation/scenarios/react_admin_access_account_center.json`（new）
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-access-account-center-public-contract-hardening/`（new）

## Contract／acceptance

1. Minimal account view只含id、username、display_name、enabled、is_root、version；role/capabilities不得驅動業務選單。
2. 每個mutation回typed receipt：operation/target/resulting version/replayed/receipt identity；不再回bool。
3. 同key同payload replay完全相同；不同payload/stale為stable 409；not-found 404、auth 401/403、storage 503
   不洩漏內部error文字。
4. actor root、target與expected version在同一UoW lock/fresh-read；account mutation、audit、receipt、必要SecurityOutbox
   一次commit，failure 0 write。
5. timeout retry保持同一idempotency key；root self-protection與last-root invariants不能由UI推導。
6. React移除mock users/email/IP/jobs、fake QR/secret與alert/confirm；Audit/Jobs tabs保留原位置並明確
   unavailable，等待各自successor。MFA setup/reset UI亦維持unavailable；Phase2C登入TOTP verify不得冒充enrollment。
7. strict Zod、真TOTP browser root/non-root、CAS/replay/session revoke、disposable MySQL rollback與secret scan通過。

本包不改DB schema；若receipt/outbox需要schema，固定`DB_SCOPE_REQUIRED`並另立DB WP。

| DB Gate | Status |
|---|---|
| Scope | PASS |
| Change inventory | PASS（0 schema/seed/backfill/destructive） |
| Static/Descriptor/Plan/Engine/Developer acceptance | NOT_RUN |

結論：`DB_CHANGE_NOT_READY`。
