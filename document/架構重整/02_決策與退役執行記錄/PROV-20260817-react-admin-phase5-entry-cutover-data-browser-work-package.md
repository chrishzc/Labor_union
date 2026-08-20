---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-data-browser
date: 2026-08-17
owner: Access / Entry Governance Integration Owner
domain: Access / Data Browser
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening PASS; PROV-20260817-react-admin-phase3d-db-r-react PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Data Browser Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Data Browser entry readiness／query candidate工作包

## Identity與範圍

Streamlit `ui:01_data_browser.py`／rollback `data-browser`／React主candidate
`ui-react:#data-browser`。舊頁內嵌的國定假日管理只可導向`ui-react:#scheduling`，不得冒充本entry已完整替代。
本包只做readiness candidate evidence；production page/client/API不在write set。Data Browser typed query、server masking與
source-correction須先由獨立successor完成。

## Exact write set

- `ui_react/src/tests/data_browser_entry_cutover.test.tsx`（new）
- `tests/test_react_data_browser_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-data-browser/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

## 必要門

1. 六個source tabs、搜尋、refresh、detail Drawer與copy action皆有stable ID；copy不得用`alert()`假成功。
2. server allowlist、pagination與PII redaction逐欄凍結；raw payload不穿透DOM、log或receipt。
3. 真TOTP browser覆蓋success／empty／unknown table／401／403／schema mismatch及Streamlit same-scope oracle。
4. source-correction Preview／Apply保持native disabled，Network證明0 POST／PATCH。
5. `/?entry=data-browser`精確rollback；holidays owner未裁決前只可標`query-candidate`，不得標full replacement。
6. Part 00 controlled scenarios、focused/full tests、build/lint、UTF-8、diff、secret/PII scan全部通過。

Current page任何embedded business row、`mockData` dependency、raw payload DOM或`alert()`固定
`BLOCKED_MOCK_REMAINDER`；因本包禁止修改production page/client，命中即停止candidate判定，不得用fixture
或snapshot掩蓋。Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（0 DB change），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
