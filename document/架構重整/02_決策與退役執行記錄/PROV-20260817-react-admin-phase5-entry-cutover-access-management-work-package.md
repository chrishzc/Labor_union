---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-access-management
date: 2026-08-17
owner: Access / Entry Governance Integration Owner
domain: Access
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-access-account-center-public-contract-hardening PASS; PROV-20260817-access-audit-public-query-hardening PASS; PROV-20260817-react-admin-phase3c-access-audit-react PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-public-outcome-contract PASS; PROV-20260817-react-admin-phase3c-durable-job-observability-react PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Access Management Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Access Management entry readiness／query candidate工作包

## Identity與範圍

Streamlit `ui:09_access_management.py`／rollback `access-management`／React
`ui-react:#account-management`。Phase2C Login/TOTP只證明認證邊界，不等於帳號管理entry已完成。
production Account page/client須由獨立Access public contract successor先完成。

Account page的shared integration順序固定為Account Center → Access Audit React → Durable Job observability。
三者各自的backend/public contract與React receipt都須PASS；MFA enrollment/self-service仍非本entry已完成能力，
不得用Phase2C登入成功冒充Account Center的TOTP管理。

## Exact write set

- `ui_react/src/tests/account_management_entry_cutover.test.tsx`（new）
- `tests/test_react_account_management_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-access-management/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；若預期需要改它，固定
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`readiness-candidate`，不得標cutover／replacement／active。

## 必要門

1. users、audit、jobs、MFA逐欄/capability/redaction matrix凍結；root-only政策由server判斷；MFA未有獨立
   successor時原位unavailable。
2. account create/enable/password reset/MFA reset/session revoke未有typed receipt前全數native disabled，0 local mutation。
3. provisioning URI、secret、QR seed、recovery codes永不進DOM、log、fixture、snapshot或receipt。
4. 真TOTP browser覆蓋root/non-root、401/403/404/409/rate-limit、disabled root及session expiry。
5. 0 fake users/audit/jobs，0 `alert/confirm`；same-scope Streamlit oracle與`/?entry=access-management`rollback。
6. 未閉合mutation時最高只可標`query-candidate`，不得標full replacement。

Current page若仍命中embedded users/audit/jobs、local create/enable/revoke/TOTP、`alert/confirm`或明文secret，
固定`BLOCKED_MOCK_REMAINDER`；test-only改動不得把它降級為warning。Queue、manifest與readiness matrix只由
Integration Owner串行更新，writer不得自行標READY。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（0 DB change），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
